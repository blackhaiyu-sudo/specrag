# 开源说明

本仓库定位为 SpecRAG 的开源版本。SpecRAG 面向 PRD、业务规则、流程制度、SOP、产品截图和其他业务文档，提供知识单元清洗、检索和基于证据的问答能力。

## 开源范围

- 文本业务文档导入
- 图片需求/流程截图导入
- 文档清洗为结构化知识单元
- query hints 生成
- PostgreSQL + Qdrant 企业存储，作为默认知识库后端
- SQLite 本地知识库，作为显式开发模式
- 基于 MCP 的问答测试

## 不包含内容

- 旧版测试用例/任务管理链路
- 业务专属历史数据
- 本地 API Key 文件
- 运行时输出和日志
- 内部域名、客户数据和私有数据

## 发布前检查

- 如果历史提交中出现过密钥，创建全新仓库或清理 Git 历史。
- `config/OAI_CONFIG_LIST` 只保留在本地。
- `.env` 只保留在本地。
- 不提交 `data/`、`runtime/`、`uploads/`、`outputs/`、`logs/`。

## 建议仓库物料

- `README.md`：中文项目概览、快速开始、存储模式和文档入口。
- `README.en.md`：英文项目概览。
- `docs/`：中文使用、架构、API 和部署文档。
- `docs/en/`：英文使用、架构、API 和部署文档。
- `LICENSE`：项目许可证。
- `CONTRIBUTING.md`：开发环境和贡献规则。
- `SECURITY.md`：密钥处理和安全问题报告说明。
- `CODE_OF_CONDUCT.md`：社区行为准则。
- `.env.example`：不含密钥的环境变量模板，默认使用企业存储。
- `config/OAI_CONFIG_LIST.example`：不含密钥的 OpenAI-compatible 模型配置模板。
- `.github/ISSUE_TEMPLATE/`：结构化问题和需求模板。
- `.github/pull_request_template.md`：PR 检查清单。

## 发布清单

- 对最终仓库历史运行密钥扫描。
- 确认运行时数据没有被提交到 Git。
- 验证 `docker compose up -d` 能启动 PostgreSQL、Qdrant 和应用。
- 验证源码启动流程：先运行 `docker compose -f docker-compose.kb-enterprise.yml up -d`，再运行 `python app.py`。
- 检查文档中是否仍有内部域名、客户名称、截图和私有模型地址。
