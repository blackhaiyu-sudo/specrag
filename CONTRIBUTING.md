# 贡献指南

感谢你关注并改进 SpecRAG。

## 开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
docker compose -f docker-compose.kb-enterprise.yml up -d
python app.py
```

## 代码规则

- 业务示例保持通用，不写入客户名、项目名和内部域名。
- 不提交本地文档、图片、运行时输出、日志或模型凭证。
- Prompt 模板放在 `agents/qa_agents/templates/`。
- 在可行范围内保持 API 行为向后兼容。
- 修改存储、检索或清洗逻辑时，补充聚焦的测试或验证脚本。

## 安全要求

不要提交：

- `config/OAI_CONFIG_LIST`
- `.env`
- `data/`
- `runtime/`
- `uploads/`
- `outputs/`
- `logs/`
