# API 参考

所有接口响应都使用统一响应结构：

```json
{
  "success": true,
  "data": {}
}
```

## 导入文本 PRD

`POST /api/kb/v1/documents/import-text-prd`

该接口也可用于导入业务规则、流程制度、SOP、操作手册等纯文本业务文档。接口名保留 `prd` 是为了兼容旧版本。

请求体：

```json
{
  "title": "示例PRD",
  "content": "# PRD ...",
  "product": "unknown",
  "version": "unknown",
  "module": "示例功能",
  "change_type": "unknown",
  "rebuild": true
}
```

## 导入图片文档

`POST /api/kb/v1/documents/import-images-prd`

该接口可用于导入产品截图、设计稿截图、业务流程截图等图片资料。接口名保留 `prd` 是为了兼容旧版本。

表单字段：

- `title`
- `description`
- `notes`
- `images[]`

## 导入已清洗 JSON

`POST /api/kb/v1/documents/import-json`

```json
{
  "json_path": "runtime/kb_imports/demo/with_hints.json",
  "rebuild": false
}
```

## 获取文档列表

`GET /api/kb/v1/documents`

## 获取文档知识单元

`GET /api/kb/v1/documents/{doc_id}/units`

## 统计信息

`GET /api/kb/v1/stats`

## 检索知识单元

`POST /api/kb/v1/retrieval/search`

```json
{
  "query": "这个功能有哪些限制？",
  "top_k": 5
}
```

可选字段：

- `product`
- `version`
- `module`
- `vector_types`
- `candidate_k`
- `evidence_k`
- `min_score`

## 普通问答

`POST /api/kb/v1/retrieval/ask`

```json
{
  "question": "这个功能有哪些限制？",
  "judge": "llm",
  "top_k": 5
}
```

## MCP 问答

`POST /api/kb/v1/retrieval/agent-ask`

该接口会执行完整的检索、证据判断和答案整合流程。

```json
{
  "question": "这个功能有哪些限制？",
  "top_k": 8,
  "product": "unknown",
  "version": "unknown"
}
```

## 添加反馈问法

`POST /api/kb/v1/feedback/query-hints`

```json
{
  "doc_id": "kb_text_20260615_demo",
  "unit_id": "RU-001",
  "query": "用户实际问法"
}
```

## 页面辅助接口

Web 页面还会使用：

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
