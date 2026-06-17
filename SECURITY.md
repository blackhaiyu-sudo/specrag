# 安全策略

## 密钥

本项目通过 `config/OAI_CONFIG_LIST` 使用 OpenAI-compatible 模型凭证。

不要提交真实凭证。仓库只保留：

- `config/OAI_CONFIG_LIST.example`
- `.env.example`
- `.env.kb-enterprise.example`

## 敏感数据

导入的 PRD、截图、清洗 JSON、向量、日志和审计轨迹都可能包含业务敏感信息。以下目录不要提交到 Git：

- `data/`
- `runtime/`
- `uploads/`
- `outputs/`
- `logs/`

## 报告安全问题

报告安全问题时，不要在公开 issue 中贴出凭证、私有文档或截图。请提供不包含敏感数据的最小复现信息。
