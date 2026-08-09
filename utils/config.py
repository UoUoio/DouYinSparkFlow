import os, sys
from enum import Enum
import base64
import json
import logging
from utils.logger import setup_logger

logger = setup_logger(level=logging.DEBUG)

"""
是否启用调试模式
更详细的日志打印，浏览器操作可视化等
"""
DEBUG = True
config = None
userData = None
_configBundle = None


class Environment(Enum):
    GITHUBACTION = "GITHUB_ACTION"  # GitHub Action 运行
    LOCAL = "LOCAL"  # 本地代码运行
    PACKED = "PACKED"  # PyInstaller 打包运行

    def __str__(self):
        return self.value


def get_environment():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Environment.PACKED
    elif os.getenv("GITHUB_ACTIONS") == "true":
        return Environment.GITHUBACTION
    else:
        return Environment.LOCAL


def _load_config_bundle():
    """
    读取打包配置：允许把 PROXY_ADDRESS / MESSAGE_TEMPLATE / TASKS 等所有配置打包成一个
    JSON 对象，只配一个变量，不用再一条条手动新增变量/密钥。

    支持两种来源：
    - CONFIG_JSON：原始 JSON 文本，用于直接粘贴进 GitHub Secret（人眼可读、方便核对）。
    - CONFIG_JSON_B64：CONFIG_JSON 的 base64 编码，用于本地 .env 部署。原因是 .env 由
      python-dotenv 按 KEY=VALUE 逐行解析，JSON 里常见的 # （比如消息模板/好友昵称里的
      "#话题#"）会被当成行内注释截断内容，用引号包裹又会被 JSON 内部可能出现的单引号破坏，
      所以本地 .env 场景统一用 base64 规避这些解析边界问题。
    """
    global _configBundle

    if _configBundle is not None:
        return _configBundle

    bundle = {}
    raw = os.getenv("CONFIG_JSON", "")
    raw_b64 = os.getenv("CONFIG_JSON_B64", "")

    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                bundle = parsed
            else:
                logger.warning("CONFIG_JSON 不是一个 JSON 对象，已忽略")
        except json.JSONDecodeError as e:
            logger.warning(f"CONFIG_JSON 解析失败，已忽略：{e}")
    elif raw_b64:
        try:
            decoded = base64.b64decode(raw_b64).decode("utf-8")
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                bundle = parsed
            else:
                logger.warning("CONFIG_JSON_B64 解码后不是一个 JSON 对象，已忽略")
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"CONFIG_JSON_B64 解析失败，已忽略：{e}")

    _configBundle = bundle
    logger.debug(f"当前 CONFIG_JSON（可直接复制修改后回填）：\n{json.dumps(bundle, ensure_ascii=False, indent=2)}")
    return _configBundle


def _pick(key, bundle, caster=None, default=None):
    """
    取配置项：优先用单独设置的同名环境变量（方便按需覆盖某一项），
    其次用 CONFIG_JSON 里打包的值，都没有则用默认值。
    """
    if key in os.environ:
        value = os.environ[key]
    elif key in bundle:
        value = bundle[key]
    else:
        return default

    if caster is not None and isinstance(value, str):
        return caster(value)
    return value


def get_config():
    """
    获取配置信息
    :return: 配置字典
    """
    global config

    if config:
        return config

    bundle = _load_config_bundle()

    config = {
        "proxyAddress": _pick("PROXY_ADDRESS", bundle, default=""),
        "messageTemplate": _pick(
            "MESSAGE_TEMPLATE", bundle,
            default="[盖瑞]今日火花[加一]\\n—— [右边] 每日一言 [左边] ——\\n[API]",
        ),
        "hitokotoTypes": _pick(
            "HITOKOTO_TYPES", bundle, caster=json.loads,
            default=["文学", "影视", "诗词", "哲学"],
        ),
        "matchMode": _pick("MATCH_MODE", bundle, default="nickname"),  # 是否使用短 ID 进行好友匹配
        "browserTimeout": int(_pick("BROWSER_TIMEOUT", bundle, default=120000)),  # 浏览器操作超时时间，单位毫秒
        "friendListTimeout": int(_pick("FRIEND_LIST_WAIT_TIME", bundle, default=2000)),  # 好友列表加载超时时间，单位毫秒
        "taskRetryTimes": int(_pick("TASK_RETRY_TIMES", bundle, default=3)),  # 任务重试次数
        "sendInterval": float(_pick("SEND_INTERVAL", bundle, default=5)),  # 每条消息发送后的等待间隔，单位秒，用于控制发送频率避免触发风控
        "logLevel": _pick("LOG_LEVEL", bundle, default="DEBUG"),  # 日志级别
    }

    return config

def sanitize_cookies(cookies):
    for cookie in cookies:
        if "sameSite" in cookie:
            cookie.pop("sameSite")  # 移除 sameSite 字段，Playwright 可能不支持该字段
    return cookies


def get_userData():
    """
    获取用户数据目录
    :return: 用户数据目录路径
    """
    global userData

    if userData:
        return userData

    bundle = _load_config_bundle()
    tasks = _pick("TASKS", bundle, caster=json.loads, default=[])

    userData = []

    for task in tasks:
        username = task.get("username", "未知用户")
        unique_id = task.get("unique_id")
        if not unique_id:
            logger.warning(f"{username} 的任务  缺少 unique_id 字段，已跳过")
            continue

        # cookies 可以直接写在 TASKS 里该任务的 cookies 字段中（推荐，配合 CONFIG_JSON 一次配完），
        # 也可以像之前一样单独设置 COOKIES_<抖音号> 环境变量，两种方式二选一即可
        inline_cookies = task.get("cookies")
        if inline_cookies:
            if isinstance(inline_cookies, str):
                try:
                    cookies = json.loads(inline_cookies)
                except json.JSONDecodeError:
                    logger.warning(f"{username} 的任务 内嵌 cookies 字段格式不正确，已跳过")
                    continue
            else:
                cookies = inline_cookies
        else:
            cookies_key = f"cookies_{unique_id}".upper()
            cookies_str = (
                os.getenv(cookies_key, "").encode("utf-8").decode("unicode_escape")
            )
            if not cookies_str:
                logger.warning(
                    f"{username} 的任务缺少 cookies（可在 TASKS 中内嵌 cookies 字段，或设置 {cookies_key} 环境变量），已跳过"
                )
                continue
            try:
                cookies = json.loads(cookies_str)
            except json.JSONDecodeError:
                logger.warning(f"{username} 的任务 {cookies_key} 格式不正确，已跳过")
                continue

        userData.append(
            {
                "unique_id": unique_id,
                "username": username,
                "cookies": sanitize_cookies(cookies),
                "targets": task.get("targets", []),
            }
        )

    return userData
