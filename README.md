# SpecRAG（业务规格知识库）

SpecRAG 是一个面向 PRD、业务规则、流程制度、SOP、产品截图和其他业务文档的证据型知识库。

它可以把文本业务文档或多张产品/流程截图转换为“知识库源文档”，再清洗为结构化知识单元，生成 query hints，写入向量知识库，并通过 MCP Agent 做证据检索、no-answer 判断和答案整合。

[English README](README.en.md)

## 适用场景

- 产品 PRD、版本需求、功能说明
- 业务规则、运营规则、审核规则
- 流程制度、SOP、操作手册
- 客服知识、实施指南、培训材料
- 接口说明、配置说明、系统使用说明
- 产品截图、设计稿截图、业务流程截图

## 核心流程

1. 导入图片、PRD 或其他业务文档
2. 生成或保存知识库源文档
3. LLM 清洗为结构化知识单元 JSON
4. 生成 query hints 和 key terms
5. 向量化并写入存储
6. 使用 MCP Agent 检索、判断证据、整合答案

## 功能特性

- 文本业务文档导入
- 图片需求/流程截图导入和多图整合
- LLM 清洗为 knowledge units
- query hints 初始化
- 多向量入库
- PostgreSQL + Qdrant 企业存储（默认）
- SQLite 本地开发存储（可选）
- MCP Agent 问答测试
- 耗时和 token 统计

## 技术栈

- 后端：Flask + SQLAlchemy
- 前端：Vue 2 + Element UI
- LLM Agent：pyautogen + OpenAI-compatible Chat Completions API
- 默认知识库存储：PostgreSQL + Qdrant
- 可选本地存储：SQLite
- 向量模型：sentence-transformers 兼容模型
- MCP：`mcp` Python SDK

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
docker compose -f docker-compose.kb-enterprise.yml up -d
python app.py
```

启动后访问：

```text
http://localhost:5002
```

## 模型配置

编辑 `config/OAI_CONFIG_LIST`，至少准备：

- 文本模型：用于文档清洗、问法生成、证据判断和答案整合。
- 视觉模型：用于图片需求、流程截图和产品截图分析。

仓库只保留 `config/OAI_CONFIG_LIST.example`。真实 API Key 请放在本地 `config/OAI_CONFIG_LIST`，该文件已被 `.gitignore` 忽略。

## 存储模式

知识库存储默认使用 PostgreSQL + Qdrant。`.env.example` 已包含本地 Docker 依赖的默认连接：

```text
KB_STORAGE_MODE=enterprise
KB_POSTGRES_DSN=postgresql://specrag:specrag_dev@127.0.0.1:15432/specrag
KB_QDRANT_URL=http://127.0.0.1:6333
KB_QDRANT_COLLECTION=specrag_units
```

本地启动企业存储依赖：

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

如只做本地小规模验证，也可以显式改为 SQLite：

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```

## 文档

- [快速开始](docs/GETTING_STARTED.md)
- [架构说明](docs/ARCHITECTURE.md)
- [API 参考](docs/API.md)
- [部署说明](docs/DEPLOYMENT.md)
- [开源说明](OPEN_SOURCE.md)
- [安全策略](SECURITY.md)
- [行为准则](CODE_OF_CONDUCT.md)
- [English docs](docs/en/GETTING_STARTED.md)

## 项目结构

```text
agents/qa_agents/templates/   Agent prompt 模板
routes/                       Flask API 路由
services/generation/          图片分析与文档整合
services/kb/                  清洗、向量化、检索、MCP 问答
services/kb/storage/          PostgreSQL + Qdrant / SQLite 存储适配
services/prd/                 文本文档管理
services/requirement_modules/ 图片需求/截图模块管理
static/                       前端静态资源
templates/                    页面模板
docs/                         设计和使用文档
```

## 运行时目录

- `runtime/`、`data/`、`uploads/`、`outputs/`、`logs/` 都是运行时目录，不应提交。
- `config/OAI_CONFIG_LIST` 是本地密钥配置，不应提交。

## 许可证

见 [LICENSE](LICENSE)。
