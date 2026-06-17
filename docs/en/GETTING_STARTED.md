# Getting Started

## 1. Prepare Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Models

Copy the example files:

```bash
cp config/OAI_CONFIG_LIST.example config/OAI_CONFIG_LIST
cp .env.example .env
```

Edit `config/OAI_CONFIG_LIST` and configure at least:

- One text model
- One vision model

## 3. Start Enterprise Storage

The default KB backend is PostgreSQL + Qdrant:

```bash
docker compose -f docker-compose.kb-enterprise.yml up -d
```

## 4. Run the App

```bash
python app.py
```

Open:

```text
http://localhost:5002
```

## 5. What You Can Do

- Import text PRDs
- Import business rules, process policies, SOPs, and other business documents
- Import requirement images or workflow screenshots and generate source knowledge documents
- View cleaned knowledge units
- Search and ask questions in the KB page

## Optional: SQLite Local Mode

For small local demos without PostgreSQL and Qdrant, edit `.env`:

```text
KB_STORAGE_MODE=sqlite
PRD_UNIT_KB_DB=data/specrag.db
```
