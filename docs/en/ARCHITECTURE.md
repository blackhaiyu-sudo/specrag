# SpecRAG Architecture

## Goal

SpecRAG is a knowledge-base import and QA service for PRDs, business rules, process policies, SOPs, product screenshots, and other business documents.

Its goal is not to generate final human-facing documents. Instead, it converts images or text business documents into knowledge-base data that can be retrieved, cited, and answered strictly from evidence.

## Main Flow

```text
Images / PRDs / business documents
  -> source knowledge document
  -> knowledge-unit cleaning
  -> query_hints generation
  -> vector indexing
  -> MCP Agent retrieval, judgment, and synthesis
```

## Inputs

### Images

Users can upload requirement images, product design screenshots, or workflow screenshots. The system first analyzes images with a vision model, then uses an image consolidation agent to generate a source knowledge document.

The intermediate document preserves cross-image context. Directly extracting units from images can lose relationships between screenshots; a source document gives the cleaning agent a continuous text representation.

### Text Documents

Users can upload Markdown or plain text business documents, including PRDs, business rules, process policies, SOPs, operation manuals, and API docs. The system performs narrow cleanup only and does not rewrite business facts.

## Knowledge Units

Knowledge units are the core factual granularity of the KB.

A unit should express a relatively complete business rule, feature action, exception handling rule, permission rule, data rule, operation step, or process fragment. It should be independently useful for retrieval and QA.

Current schema:

```json
{
  "unit_id": "RU-001",
  "title": "Short title",
  "unit_type": "feature",
  "content": "Complete requirement or rule",
  "rules": ["Rule 1", "Rule 2"],
  "source": {
    "heading_path": ["Section path"],
    "start_line": 1,
    "end_line": 10
  },
  "retrieval_meta": {
    "query_hints": ["Likely user wording"],
    "key_terms": ["Original evidence terms"]
  }
}
```

`content` and `rules` are answer evidence. `query_hints` improve retrieval but must not be treated as factual evidence.

## Vector Design

Each unit can produce multiple vector texts:

- `body`: title, body, rules, and section context for base semantic retrieval.
- `agent_hint_bundle`: query hints and key terms for matching common user wording.
- `feedback_hint`: user feedback wording for continuous retrieval improvement.

Business documents and user questions often use different wording. Multi-vector indexing balances factual text and user expression.

## QA Flow

The QA flow is orchestrated by an MCP Agent:

1. `search_units`: retrieve candidate units.
2. `expand_search`: broaden search if the first round is insufficient.
3. `get_unit`: load complete unit content.
4. `judge_answerability`: decide whether evidence is sufficient.
5. `synthesize_answer`: synthesize a natural-language answer from supporting units.

The agent must call MCP tools before answering. If evidence is insufficient, it must return no-answer instead of inferring from nearby content.

## Storage Modes

### Enterprise Mode

The default mode uses PostgreSQL + Qdrant:

- PostgreSQL stores factual data: documents, knowledge units, versions, sources, feedback hints, and vector metadata.
- Qdrant stores vector indexes for high-performance semantic retrieval.

Qdrant returns candidates, but the system still reads full units from PostgreSQL before judgment and synthesis. Qdrant is not the factual source of truth.

### SQLite Mode

SQLite mode requires `KB_STORAGE_MODE=sqlite`. It stores documents, units, and vectors in one SQLite file. It is useful for local development and small demos, not as the default production shape.
