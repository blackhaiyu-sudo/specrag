# SpecRAG

SpecRAG is an evidence-grounded knowledge base for PRDs, business rules, SOPs, process documents, product screenshots, and other business documents.

It turns text documents or multiple product/process screenshots into source knowledge documents, cleans them into structured knowledge units, generates query hints, stores vectors, and uses an MCP Agent for evidence retrieval, no-answer judgment, and answer synthesis.

[中文 README](README.md)

## Use Cases

- Product PRDs, release requirements, feature specs
- Business rules, operation rules, review rules
- Process policies, SOPs, operation manuals
- Support knowledge, implementation guides, training materials
- API docs, configuration guides, system usage docs
- Product screenshots, design screenshots, workflow screenshots

## Core Flow

1. Import images, PRDs, or other business documents
2. Generate or store a source knowledge document
3. Clean it into structured knowledge-unit JSON
4. Generate query hints and key terms
5. Embed and write to storage
6. Use the MCP Agent to retrieve evidence, judge answerability, and synthesize answers

## Features

- Text business-document import
- Image and workflow-screenshot import with multi-image consolidation
- LLM-based cleaning into knowledge units
- Query hint initialization
- Multi-vector indexing
- PostgreSQL + Qdrant enterprise storage by default
- Optional SQLite local development storage
- MCP Agent QA testing
- Duration and token statistics

## Stack

- Backend: Flask + SQLAlchemy
- Frontend: Vue 2 + Element UI
- LLM Agent: pyautogen + OpenAI-compatible Chat Completions API
- Default KB storage: PostgreSQL + Qdrant
- Optional local storage: SQLite
- Embedding models: sentence-transformers compatible models
- MCP: `mcp` Python SDK

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
docker compose -f docker-compose.kb-enterprise.yml up -d
python app.py
```

Open:

```text
http://localhost:5002
```

## Model Config

Edit `config/OAI_CONFIG_LIST` and configure at least:

- A text model for document cleaning, query hint generation, evidence judgment, and answer synthesis.
- A vision model for product screenshots, workflow screenshots, and requirement images.

Only `config/OAI_CONFIG_LIST.example` is committed. Put real API keys in local `config/OAI_CONFIG_LIST`; it is ignored by Git.

## Storage

SpecRAG uses PostgreSQL + Qdrant by default. `.env.example` includes local Docker defaults:

```text
KB_STORAGE_MODE=enterprise
KB_POSTGRES_DSN=postgresql://specrag:specrag_dev@127.0.0.1:15432/specrag
KB_QDRANT_URL=http://127.0.0.1:6333
KB_QDRANT_COLLECTION=specrag_units
```

Start local storage dependencies:

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

For small local demos, explicitly switch to SQLite:

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```

## Documentation

- [Getting Started](docs/en/GETTING_STARTED.md)
- [Architecture](docs/en/ARCHITECTURE.md)
- [API Reference](docs/en/API.md)
- [Deployment](docs/en/DEPLOYMENT.md)
- [Chinese docs](README.md)

## Runtime Paths

- `runtime/`, `data/`, `uploads/`, `outputs/`, and `logs/` are runtime paths and should not be committed.
- `config/OAI_CONFIG_LIST` contains local credentials and should not be committed.

## License

See [LICENSE](LICENSE).
