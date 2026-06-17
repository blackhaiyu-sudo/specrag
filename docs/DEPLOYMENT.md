# 部署说明

## 本地源码启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
docker compose -f docker-compose.kb-enterprise.yml up -d
python app.py
```

## Docker 启动

```bash
docker compose up -d
```

默认 compose 文件会基于 `Dockerfile.prod` 构建镜像，并同时启动应用、PostgreSQL 和 Qdrant。

容器内模型配置路径为：

```text
/app/config/OAI_CONFIG_LIST
```

## 企业存储

企业存储是默认知识库后端。

关键环境变量：

- `KB_STORAGE_MODE=enterprise`
- `KB_POSTGRES_DSN`
- `KB_QDRANT_URL`

本地源码启动时，先启动存储依赖：

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

生产 Docker 部署时，`docker-compose.prod.yml` 默认使用外部 PostgreSQL 和 Qdrant 服务，并要求配置 `KB_POSTGRES_DSN` 和 `KB_QDRANT_URL`。

使用 `deploy-simple.sh` 时，先导出这些变量：

```bash
export KB_POSTGRES_DSN='postgresql://user:password@host:5432/specrag'
export KB_QDRANT_URL='http://host:6333'
./deploy-simple.sh your-server.example.com
```

## SQLite 本地模式

SQLite 只作为显式本地模式使用：

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```

## MCP 服务

Web 问答流程内部会使用 MCP。也可以直接启动 MCP 服务：

```bash
python scripts/kb_mcp_server.py --transport stdio
```

常用参数：

- `--db`
- `--model`
- `--embedding-provider sentence|hashing`
- `--judge rule|llm`
