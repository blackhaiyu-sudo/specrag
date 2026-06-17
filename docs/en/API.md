# API Reference

All endpoints use the same response wrapper:

```json
{
  "success": true,
  "data": {}
}
```

## Import Text Documents

`POST /api/kb/v1/documents/import-text-prd`

This endpoint can import PRDs, business rules, process policies, SOPs, operation manuals, and other text business documents. The path keeps `prd` for backward compatibility.

Request body:

```json
{
  "title": "Demo Document",
  "content": "# Document ...",
  "product": "unknown",
  "version": "unknown",
  "module": "Demo Module",
  "change_type": "unknown",
  "rebuild": true
}
```

## Import Image Documents

`POST /api/kb/v1/documents/import-images-prd`

This endpoint can import product screenshots, design screenshots, workflow screenshots, and requirement images. The path keeps `prd` for backward compatibility.

Form fields:

- `title`
- `description`
- `notes`
- `images[]`

## Import Cleaned JSON

`POST /api/kb/v1/documents/import-json`

```json
{
  "json_path": "runtime/kb_imports/demo/with_hints.json",
  "rebuild": false
}
```

## List Documents

`GET /api/kb/v1/documents`

## List Document Units

`GET /api/kb/v1/documents/{doc_id}/units`

## Stats

`GET /api/kb/v1/stats`

## Search Units

`POST /api/kb/v1/retrieval/search`

```json
{
  "query": "What are the limits of this feature?",
  "top_k": 5
}
```

Optional fields:

- `product`
- `version`
- `module`
- `vector_types`
- `candidate_k`
- `evidence_k`
- `min_score`

## Ask

`POST /api/kb/v1/retrieval/ask`

```json
{
  "question": "What are the limits of this feature?",
  "judge": "llm",
  "top_k": 5
}
```

## MCP QA

`POST /api/kb/v1/retrieval/agent-ask`

This endpoint runs the full retrieval, evidence judgment, and answer synthesis flow.

```json
{
  "question": "What are the limits of this feature?",
  "top_k": 8,
  "product": "unknown",
  "version": "unknown"
}
```

## Add Feedback Query Hint

`POST /api/kb/v1/feedback/query-hints`

```json
{
  "doc_id": "kb_text_20260615_demo",
  "unit_id": "RU-001",
  "query": "Actual user wording"
}
```

## Page Helper APIs

The web UI also uses:

- `POST /api/prds/upload`
- `GET /api/prds`
- `GET /api/prds/{prd_id}`
- `PUT /api/prds/{prd_id}`
- `DELETE /api/prds/{prd_id}`
- `POST /api/requirement-modules/create`
- `POST /api/requirement-modules/{module_id}/upload-images`
- `GET /api/requirement-modules`
- `GET /api/requirement-modules/{module_id}`
- `PUT /api/requirement-modules/{module_id}`
- `DELETE /api/requirement-modules/{module_id}`
