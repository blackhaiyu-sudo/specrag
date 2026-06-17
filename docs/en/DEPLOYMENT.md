# Deployment

## Local Source Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
docker compose -f docker-compose.kb-enterprise.yml up -d
python app.py
```

## Docker

```bash
docker compose up -d
```

The default compose file builds from `Dockerfile.prod` and starts the app, PostgreSQL, and Qdrant.

The model config path inside the container is:

```text
/app/config/OAI_CONFIG_LIST
```

## Enterprise Storage

Enterprise storage is the default KB backend.

Required environment variables:

- `KB_STORAGE_MODE=enterprise`
- `KB_POSTGRES_DSN`
- `KB_QDRANT_URL`

For local source runs, start storage dependencies first:

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

For production Docker deployments, `docker-compose.prod.yml` expects external PostgreSQL and Qdrant services and requires `KB_POSTGRES_DSN` and `KB_QDRANT_URL`.

When using `deploy-simple.sh`, export these values first:

```bash
export KB_POSTGRES_DSN='postgresql://user:password@host:5432/specrag'
export KB_QDRANT_URL='http://host:6333'
./deploy-simple.sh your-server.example.com
```

## SQLite Local Mode

SQLite is only an explicit local mode:

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```

## MCP Server

The web QA flow uses MCP internally. You can also run the MCP server directly:

```bash
python scripts/kb_mcp_server.py --transport stdio
```

Common options:

- `--db`
- `--model`
- `--embedding-provider sentence|hashing`
- `--judge rule|llm`
