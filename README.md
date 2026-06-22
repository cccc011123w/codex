# 基金策略邮件云端自动化

这个仓库用于在 GitHub Actions 云端每天生成基金交易策略，并通过 QQ 邮箱发送到 `1678221404@qq.com`。电脑不开机、不联网也可以运行，因为任务在 GitHub 云端执行。

## 你需要准备

- GitHub 账号
- QQ 邮箱 SMTP 授权码
- OpenAI API Key

## 使用步骤

1. 在 GitHub 新建一个私有仓库，例如 `fund-cloud-automation`。
2. 上传本目录里的所有文件，保持 `.github/workflows/daily-fund-strategy.yml` 路径不变。
3. 进入仓库 `Settings` -> `Secrets and variables` -> `Actions`。
4. 在 `Secrets` 里添加：

```text
OPENAI_API_KEY=你的 OpenAI API Key
QQMAIL_USER=1678221404@qq.com
QQMAIL_TO=1678221404@qq.com
QQMAIL_AUTH_CODE=你的 QQ 邮箱 SMTP 授权码
```

5. 可选：在 `Variables` 里添加：

```text
OPENAI_MODEL=gpt-5.5
```

6. 进入仓库 `Actions`，打开 `Daily Fund Strategy`，点击 `Run workflow` 手动测试一次。

## 定时规则

工作流现在设置为 UTC `06:30` 周一到周五运行，对应北京时间/香港时间 `14:30`。

```yaml
cron: "30 6 * * 1-5"
```

## 持仓配置

持仓在 `config/holdings.json` 中。现在已写入你的截图持仓：

- 财通品质甄选混合C
- 广发远见智选混合C
- 财通价值动量混合C
- 鹏华创新未来混合(LOF)C

如果你知道基金代码，把对应的 `"code": ""` 补成 6 位代码，脚本会尝试同步天天基金的估值/净值。例如：

```json
{
  "name": "示例基金C",
  "code": "012345"
}
```

如果代码为空，策略仍会根据基金名称、持仓浮盈和市场指数生成，但会在邮件中标注基金实时数据缺口。

## 安全提醒

不要把 `OPENAI_API_KEY`、`QQMAIL_AUTH_CODE` 写进代码或提交到仓库。只放在 GitHub Secrets。

基金策略仅供参考，不构成个性化投资顾问意见，交易风险由你自行承担。
