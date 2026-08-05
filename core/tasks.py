import traceback
from utils.logger import setup_logger
from utils.config import get_config, get_userData
from core.msg_builder import build_message, build_message_with_openai
from core.browser import get_browser
from playwright.sync_api import Response
import time
import json


complates = {}

config = get_config()
userData = get_userData()
logger = setup_logger(level=config.get("logLevel", "Info"))
matchMode = config.get("matchMode", "nickname")
userIDDict = {}

def handle_response(response: Response):
    """
    只监听你要的那个接口响应
    """
    global userIDDict
    # 精准匹配目标接口 URL
    if "aweme/v1/creator/im/user_detail/" in response.url:
        # print(f"URL: {response.url}")
        # print(f"状态码: {response.status}")
        try:
            # 获取接口返回的 JSON 数据（就是你在 Network 里看到的内容）
            json_data = response.json()
            # print("\n📦 响应 JSON 数据：")
            # print(json.dumps(json_data, indent=4, ensure_ascii=False))
            for item in json_data.get("user_list", []):
                short_id = item.get("user", {}).get("ShortId")
                nickname = item.get("user", {}).get("nickname")
                user_id = item.get("user_id", "")
                userIDDict[str(short_id)] = {"nickname": nickname, "user_id": user_id}
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            last = tb[-1]
            print(f"解析响应失败: {e}")
            print(f"文件: {last.filename}, 行号: {last.lineno}, 函数: {last.name}")


def retry_operation(name, operation, retries=3, delay=2, *args, **kwargs):
    """
    通用的重试逻辑
    :param name: 操作名称（用于日志记录）
    :param operation: 要执行的异步操作
    :param retries: 最大重试次数
    :param delay: 每次重试之间的延迟（秒）
    :param args: 传递给操作的参数
    :param kwargs: 传递给操作的关键字参数
    """
    for attempt in range(retries):
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"{name} 失败，正在重试第 {attempt + 1} 次，错误：{e}")
                time.sleep(delay)
            else:
                logger.error(f"{name} 失败，已达到最大重试次数，错误：{e}")
                raise


def scroll_and_select_user(page, username, targets):
    """尝试滚动并查找用户名"""
    # 定义目标元素和滚动容器的选择器
    friends_tab_selector = 'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]'
    target_selector = 'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]//div[contains(@class, "semi-list-item-body semi-list-item-body-flex-start")]'
    scrollable_friends_selector = 'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]/div/div/div[3]/div/div/div/ul/div'
    
    # [修复] 使用模糊匹配 no-more-tip- 前缀，不再依赖精确哈希后缀
    # 同时增加文本匹配作为兜底
    no_more_selector = 'xpath=//div[contains(@class, "no-more-tip-")]'
    loading_selector = 'xpath=//div[contains(@class, "semi-spin")]'

    logger.debug(f"账号 {username} 开始查找目标好友列表")
    logger.debug(f"账号 {username} 目标好友列表: {targets}")

    logger.debug(f"账号 {username} 点击进入好友标签页")
    # 点击好友标签页
    page.wait_for_selector(friends_tab_selector)
    page.locator(friends_tab_selector).click()

    logger.debug(f"账号 {username} 进入好友列表页面")

    # 确保第一个好友元素加载完成
    first_friend_selector = 'xpath=//*[@id="sub-app"]/div/div/div[2]/div[2]/div/div/div[1]/div/div/div/ul/div/div/div[1]/li/div'
    page.wait_for_selector(first_friend_selector)
    page.locator(first_friend_selector).click()  # 点击第一个好友，确保列表激活

    logger.debug(f"账号 {username} 已激活好友列表，开始滚动查找目标好友")

    time.sleep(config["friendListTimeout"] / 1000)  # 等待好友列表加载

    found_targets = set()
    # [修改] 复制一份目标列表用于追踪进度
    remaining_targets = set(targets)

    # [修复] 新增：连续空滚动计数器（滚动后没有发现新好友的次数）
    empty_scroll_count = 0
    MAX_EMPTY_SCROLLS = 10  # 连续10次滚动没有新好友，认为到底了

    while True:
        # 查找所有目标元素
        target_elements = page.locator(target_selector).all()

        # [修复] 记录本轮循环前已发现的好友数，用于判断是否有新发现
        prev_found_count = len(found_targets)

        for element in target_elements:
            try:
                # 查找子元素 span，模糊匹配 class
                span = element.locator(
                    """xpath=.//span[contains(@class, "item-header-name-")]"""
                )
                targetName = span.inner_text()

                if targetName in found_targets:
                    continue  # 已处理过，跳过
                found_targets.add(targetName)

                logger.debug(f"账号 {username} 找到好友 {targetName}")
                # 检查是否是目标用户名
                if matchMode == "short_id":
                    targetSymbol = next((sid for sid, info in userIDDict.items() if info.get("nickname") == targetName), None)
                else:
                    targetSymbol = targetName

                if targetSymbol in targets:
                    element.click()
                    if matchMode == "short_id":
                        logger.debug(
                            f"账号 {username} 选中目标好友 {targetName} 准备开始交互"
                        )
                    else:
                        logger.debug(
                            f"账号 {username} 选中目标好友 {targetName} (ShortId: {targetSymbol}) 准备开始交互"
                        )
                    # [容错] 同时把 targetSymbol 交给调用方，方便按 targets 里的原始标识追踪发送结果、发起补偿重试
                    yield targetSymbol, targetName
                    
                    # [修改] 标记已找到，如果全找到了直接退出
                    if targetSymbol in remaining_targets:
                        remaining_targets.remove(targetSymbol)
                    if len(remaining_targets) == 0:
                        logger.debug(f"账号 {username} 所有目标好友均已找到，停止搜索")
                        return
                    break
            except Exception as e:
                traceback.print_exc()
        else:
            # [修复] 检查本轮是否有新好友被发现
            new_found = len(found_targets) > prev_found_count
            if new_found:
                empty_scroll_count = 0  # 有新发现，重置计数器
            else:
                empty_scroll_count += 1  # 无新发现，递增计数器

            # [修复] 状态检测逻辑（多重兜底）
            
            # 1. 检查是否到底（"没有更多了" —— 使用模糊类名匹配）
            if page.locator(no_more_selector).count() > 0:
                logger.info(f"账号 {username} 检测到'没有更多了'标志，已到达底部")
                if len(remaining_targets) > 0:
                    logger.warning(f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}")
                break

            # 2. [修复] 检查连续空滚动次数，防止死循环
            if empty_scroll_count >= MAX_EMPTY_SCROLLS:
                logger.warning(f"账号 {username} 连续 {MAX_EMPTY_SCROLLS} 次滚动未发现新好友，判定已到达底部")
                if len(remaining_targets) > 0:
                    logger.warning(f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}")
                break

            # 3. 检查是否正在加载
            if page.locator(loading_selector).count() > 0:
                logger.debug(f"账号 {username} 列表正在加载中 (Loading)...")
                time.sleep(1.5) # 给加载留点时间
                # 不 break，继续去滚动以触发后续内容

            # 4. 滚动容器
            scrollable_element = page.locator(
                scrollable_friends_selector
            ).element_handle()
            
            if scrollable_element:
                # [修复] 记录滚动前的 scrollTop，用于检测是否真的滚动了
                scroll_top_before = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )
                
                page.evaluate(
                    "(element) => element.scrollTop += 800", scrollable_element
                )
                
                # [修复] 检测滚动后的 scrollTop
                time.sleep(0.3)
                scroll_top_after = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )
                
                if scroll_top_before == scroll_top_after:
                    # scrollTop 没有变化，说明已经到底了
                    empty_scroll_count += 2  # 加速判定到底
                    logger.debug(f"账号 {username} scrollTop 未变化 ({scroll_top_before})，可能已到底 (空滚动计数: {empty_scroll_count}/{MAX_EMPTY_SCROLLS})")
                else:
                    logger.debug(f"账号 {username} 滚动好友列表以加载更多好友 (scrollTop: {scroll_top_before} -> {scroll_top_after})")
                
                time.sleep(1.5)
            else:
                logger.error(f"账号 {username} 未找到滚动容器，退出")
                break


def do_user_task(browser, username, cookies, targets, unique_id=None):
        record_key = unique_id or username
        # results: {targetSymbol: {"name":, "status":, "error":}}，用 dict 而非 list 保存，
        # 这样账号级补偿重试重复调用本函数时可以直接按 targetSymbol 覆盖旧记录，不会产生重复项
        results = complates.setdefault(record_key, {})

        context = browser.new_context()  # 每个任务使用独立的上下文
        context.set_default_navigation_timeout(config["browserTimeout"])  # 设置导航超时时间为 120 秒
        context.set_default_timeout(config["browserTimeout"])  # 设置所有操作的默认超时时间为 120 秒

        page = context.new_page()

        def _attempt_targets(target_list):
            """对给定好友列表尝试发送一轮消息，返回 {targetSymbol: {"name":, "status":, "error":}}"""
            status_map = {}
            for target_symbol, target_name in scroll_and_select_user(page, username, target_list):
                # [容错] 单个好友发送失败不应影响其余好友，捕获异常后记录并继续下一个
                try:
                    logger.debug(f"账号 {username} 已选中好友 {target_name} 发送消息")
                    # 等待聊天输入框元素加载完成，使用更稳定的属性选择器
                    chat_input_selector = "xpath=//div[contains(@class, 'chat-input-')]"
                    page.wait_for_selector(chat_input_selector, timeout=config["browserTimeout"])
                    chat_input = page.locator(chat_input_selector)

                    message = build_message()
                    lines = message.split("\\n")

                    def _send_message():
                        # 先清空输入框，避免重试时把上一次未发送成功的内容重复拼接进去
                        chat_input.fill("")
                        # 在 chat-input-dccKiL 中输入内容
                        for index, line in enumerate(lines):
                            chat_input.type(line)  # 输入每一行
                            # 如果不是最后一行，模拟 Shift+Enter 插入换行
                            if index != len(lines) - 1:
                                chat_input.press("Shift+Enter")  # 模拟 Shift+Enter 插入换行
                        # 模拟按下回车键发送消息
                        chat_input.press("Enter")

                    logger.debug(
                        f"账号 {username} 准备发送消息给好友 {target_name}：\n\t{message}"
                    )
                    # [容错] 发送过程本身也走重试逻辑，应对偶发的元素未就绪等瞬时错误
                    retry_operation(
                        f"账号 {username} 给好友 {target_name} 发送消息",
                        _send_message,
                        retries=config["taskRetryTimes"],
                        delay=config["sendInterval"],
                    )

                    logger.info(f"账号 {username} 给好友 {target_name} 发送消息成功")
                    status_map[target_symbol] = {"name": target_name, "status": "success"}
                except Exception as e:
                    logger.error(
                        f"账号 {username} 给好友 {target_name} 发送消息失败，错误：{e}"
                    )
                    status_map[target_symbol] = {
                        "name": target_name,
                        "status": "failed",
                        "error": str(e),
                    }
                finally:
                    # [频率限制] 无论成功失败，发送后都按配置的间隔等待，避免触发风控
                    time.sleep(config["sendInterval"])
            return status_map

        try:
            if matchMode == "short_id":  # 使用抖音号进行匹配
                page.on("response", handle_response)

            # 打开抖音创作者中心
            retry_operation(
                "打开抖音创作者中心",
                page.goto,
                retries=config["taskRetryTimes"],
                delay=5,
                url="https://creator.douyin.com/",
            )
            # 注入 Cookie
            context.add_cookies(cookies)

            # 导航到消息页面
            retry_operation(
                "导航到消息页面",
                page.goto,
                retries=config["taskRetryTimes"],
                delay=5,
                url="https://creator.douyin.com/creator-micro/data/following/chat",
            )

            logger.debug(f"账号 {username} 开始发送消息")

            # [容错补偿] 好友维度的补偿重试：一轮扫描后仍失败、或压根没在好友列表里扫到的好友，
            # 会在接下来的几轮里重新扫描好友列表、重新尝试发送，而不是扫一遍找不到就直接放弃
            target_status = {}
            pending_targets = list(dict.fromkeys(targets))  # 去重并保留原始顺序
            max_rounds = max(1, config["taskRetryTimes"])
            for round_index in range(1, max_rounds + 1):
                if not pending_targets:
                    break
                if round_index > 1:
                    logger.warning(
                        f"账号 {username} 第 {round_index}/{max_rounds} 轮补偿重试，待处理好友: {pending_targets}"
                    )
                round_status = _attempt_targets(pending_targets)
                target_status.update(round_status)
                # 本轮仍失败、或没在列表里扫到（不在 round_status 里）的好友，进入下一轮
                pending_targets = [
                    t for t in pending_targets
                    if round_status.get(t, {}).get("status") != "success"
                ]

            # 补偿轮次用尽后仍处理不了的好友，明确记为失败，避免被静默丢弃
            for target in pending_targets:
                target_status.setdefault(
                    target,
                    {
                        "name": target,
                        "status": "failed",
                        "error": "多轮尝试后仍未在好友列表中找到该好友",
                    },
                )

            # 按 targetSymbol 覆盖写入，账号级补偿重试重新调用本函数时会用新结果替换旧的失败记录
            for symbol, info in target_status.items():
                results[symbol] = info

            failed_targets = [info["name"] for info in results.values() if info["status"] == "failed"]
            if failed_targets:
                logger.warning(
                    f"账号 {username} 经过最多 {max_rounds} 轮尝试，以下好友仍发送失败: {failed_targets}"
                )
        finally:
            context.close()  # 任务完成后关闭上下文（无论任务是否成功都要释放资源）


def runTasks():
    playwright, browser = get_browser()
    try:
        # 检查是否启用多任务和任务数量
        # 创建信号量以限制并发任务数量
        logger.info("开始执行任务")
        logger.debug(f"当前配置如下：")
        logger.debug(f"消息模板: {config.get('messageTemplate', '未找到消息模板')}")
        logger.debug(f"一言类型: {config['hitokotoTypes']}")
        for user in userData:
            logger.debug(f"用户: {user.get('username', '未知用户')}, 目标好友: {user['targets']}")

        # [容错补偿] 账号级补偿重试：每一轮只重新处理"该账号里还没发送成功"的好友，
        # 已经成功的好友不会被再次选中发送，避免重复发消息
        max_account_rounds = max(1, config["taskRetryTimes"])
        pending_users = list(userData)

        for round_index in range(1, max_account_rounds + 1):
            if not pending_users:
                break
            if round_index > 1:
                logger.warning(
                    f"进行第 {round_index}/{max_account_rounds} 轮账号级补偿重试，"
                    f"待处理账号: {[u.get('username', '未知用户') for u in pending_users]}"
                )

            next_pending = []
            for user in pending_users:
                cookies = user["cookies"]
                unique_id = user["unique_id"]
                username = user.get("username", "未知用户")

                if round_index == 1:
                    complates[unique_id] = {}  # 初始化该账号的发送结果记录
                    targets_to_send = user["targets"]
                    logger.info(f"开始处理账号 {username}")
                else:
                    prior_status = complates.get(unique_id, {})
                    # 只挑出还没成功的好友重试，已成功的不再发送
                    targets_to_send = [
                        t for t in user["targets"]
                        if prior_status.get(t, {}).get("status") != "success"
                    ]
                    if not targets_to_send:
                        continue
                    logger.info(
                        f"账号 {username} 补偿重试第 {round_index} 轮，仅重试未发送成功的好友: {targets_to_send}"
                    )

                try:
                    # 创建任务
                    do_user_task(browser, username, cookies, targets_to_send, unique_id)
                    logger.info(f"账号 {username} 任务完成")
                except Exception as e:
                    # 单个账号发生未预期的异常不应中断整批任务，记录后继续处理下一个账号
                    logger.error(f"账号 {username} 任务异常终止，错误：{e}")
                    traceback.print_exc()

                status_after = complates.get(unique_id, {})
                remaining_failed = [
                    t for t in user["targets"]
                    if status_after.get(t, {}).get("status") != "success"
                ]
                if remaining_failed and round_index < max_account_rounds:
                    next_pending.append(user)

            pending_users = next_pending

        # 汇总本次运行结果，便于排查哪些账号/好友最终仍未发送成功
        failed_accounts = []
        for user in userData:
            unique_id = user["unique_id"]
            username = user.get("username", "未知用户")
            status = complates.get(unique_id, {})
            failed_targets = [
                t for t in user["targets"] if status.get(t, {}).get("status") != "success"
            ]
            if failed_targets:
                logger.warning(
                    f"账号 {username} 经过最多 {max_account_rounds} 轮补偿重试，以下好友最终仍未发送成功: {failed_targets}"
                )
                failed_accounts.append(username)
        if failed_accounts:
            logger.warning(f"以下账号存在未能成功发送的好友: {failed_accounts}")
    finally:
        # 关闭浏览器实例
        browser.close()

        playwright.stop()

        

