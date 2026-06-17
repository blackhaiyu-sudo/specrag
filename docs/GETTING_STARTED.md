# 快速开始

## 1. 准备 Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置模型

复制示例配置：

```bash
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
```

编辑 `config/OAI_CONFIG_LIST`，至少配置：

- 一个文本模型
- 一个视觉模型

## 3. 启动企业存储

知识库后端默认使用 PostgreSQL + Qdrant：

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

## 4. 启动应用

```bash
python app.py
```

访问：

```text
http://localhost:5002
```

## 5. 可用能力

- 导入文本 PRD
- 导入业务规则、流程制度、SOP 等业务文档
- 导入图片需求/流程截图并生成知识库源文档
- 查看清洗后的知识单元
- 在知识库页面检索和问答

## 可选：SQLite 本地模式

如果只是做小规模本地 demo，不想启动 PostgreSQL 和 Qdrant，可以编辑 `.env`：

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```
