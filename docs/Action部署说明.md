# Github Action 部署

> 前提：先完成 [配置生成器使用](配置生成器使用.md)，拿到 `CONFIG_JSON`

## 第1步：Fork 仓库

打开本项目主页 → 右上角 `Fork`

## 第2步：启用 Workflow

进入 Fork 后的仓库 → `Actions` 标签页 → 启用工作流

![启用workflow](images/启用workflow.png)

![启用action](images/启用action.png)

## 第3步：创建 Environment

`Settings` → `Environments` → `New environment` → 名称填 `user-data` → 创建

![创建user-data环境图](images/屏幕截图%202026-02-14%20224915.png)

## 第4步：添加 Secret

`Settings` → `Environments` → `user-data` → `Environment secrets` → `Add secret`

- Name：`CONFIG_JSON`
- Value：粘贴配置生成器生成的 JSON
- 类型选 **Secret**（不要选 Variable，里面含 Cookies）

![配置生成器](images/配置生成器.png)

> 只想临时改一项配置（比如日志级别）？额外加一个同名 Secret/Variable 即可，优先级更高。

## 第5步（可选）：修改执行时间

编辑 `.github/workflows/schedule.yml`：

```yaml
schedule:
  - cron: "1 16 * * *" # UTC 时间，对应北京时间 00:01
```

GitHub Actions 用 UTC 时区，北京时间 = UTC + 8 小时。不会换算可以直接问 AI。

## 第6步：手动触发测试

`Actions` 页面手动运行一次，确认成功后即可等待每日自动执行

![手动测试](images/屏幕截图%202026-02-14%20224614.png)
