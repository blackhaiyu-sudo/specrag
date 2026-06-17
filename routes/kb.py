"""Knowledge-base API routes."""

from __future__ import annotations

import os
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import request

from utils.response import error_response, success_response


DEFAULT_UNIT_JSON = os.environ.get("PRD_UNIT_DEFAULT_JSON", "").strip()
DEFAULT_EMBEDDING_MODEL = os.environ.get("PRD_UNIT_EMBEDDING_MODEL", "runtime/models/qwen3-embedding-0.6b")
DEFAULT_DB_PATH = "data/specrag.db"
KB_IMPORT_OUTPUT_DIR = "runtime/kb_imports"
KB_AGENT_AUDIT_LOG = "logs/kb_agent_ask_audit.jsonl"


def register_kb_routes(app):
    unit_kb_cache = {}
    mcp_qa_agent_cache = {}

    def light_unit_kb():
        from services.kb.storage import create_kb_store

        cache_key = _kb_store_cache_key("rule", lightweight=True)
        if cache_key not in unit_kb_cache:
            unit_kb_cache[cache_key] = create_kb_store(judge="rule", lightweight=True)
        return unit_kb_cache[cache_key]

    def semantic_unit_kb(judge="rule"):
        from services.kb.storage import create_kb_store

        judge_mode = str(judge or "rule").strip().lower()
        cache_key = _kb_store_cache_key(judge_mode, lightweight=False)
        if cache_key not in unit_kb_cache:
            unit_kb_cache[cache_key] = create_kb_store(judge=judge_mode, lightweight=False)
        return unit_kb_cache[cache_key]

    def import_cleaned_json_path(cleaned_json_path, rebuild=False):
        return semantic_unit_kb(judge="rule").import_cleaned_json(cleaned_json_path, rebuild=rebuild)

    def mcp_qa_agent():
        from services.kb.prd_mcp_qa_agent import PRDKBMCPQAAgent

        cache_key = "default"
        if cache_key not in mcp_qa_agent_cache:
            mcp_qa_agent_cache[cache_key] = PRDKBMCPQAAgent()
        return mcp_qa_agent_cache[cache_key]

    @app.route("/api/kb/v1/documents/import-json", methods=["POST"])
    def import_requirement_unit_json():
        try:
            data = request.get_json(silent=True) or {}
            cleaned_json = str(data.get("json_path") or data.get("cleaned_json") or DEFAULT_UNIT_JSON).strip()
            if not cleaned_json:
                return error_response("缺少必要参数: json_path", 400)
            result = import_cleaned_json_path(cleaned_json, rebuild=bool(data.get("rebuild", False)))
            return success_response(result)
        except Exception as exc:
            return error_response(f"导入知识单元 JSON 失败: {exc}", 500)

    @app.route("/api/kb/v1/documents/import-text-prd", methods=["POST"])
    def import_text_prd_to_kb():
        try:
            data = request.get_json(silent=True) or {}
            content = str(data.get("content") or "").strip()
            if not content:
                return error_response("缺少必要参数: content", 400)
            metadata = _document_metadata_from_payload(data, source_prefix="kb_text")
            result = _clean_hint_and_import_prd(
                prd_content=content,
                metadata=metadata,
                import_cleaned_json=import_cleaned_json_path,
                rebuild=bool(data.get("rebuild", False)),
            )
            return success_response(result)
        except Exception as exc:
            return error_response(f"导入文本 PRD 到知识库失败: {exc}", 500)

    @app.route("/api/kb/v1/documents/import-images-prd", methods=["POST"])
    def import_images_prd_to_kb():
        try:
            files = request.files.getlist("images")
            if not files:
                return error_response("缺少上传图片: images", 400)
            title = str(request.form.get("title") or "").strip()
            if not title:
                return error_response("缺少必要参数: title", 400)

            from services.requirement_modules.requirement_module_service import RequirementModuleService
            from services.generation.image_pipeline_service import ImagePipelineService

            module_service = RequirementModuleService()
            module_id = module_service.create_module(title, request.form.get("description"))
            if request.form.get("notes"):
                module_service.update_module(module_id, notes_requirement=request.form.get("notes"))
            upload_result = module_service.upload_images(module_id, files)
            if upload_result.get("uploaded", 0) <= 0:
                return error_response(f"图片上传失败: {upload_result.get('failed')}", 400)

            image_service = ImagePipelineService()
            image_logger = _NoopPipelineLogger()
            analyses = image_service._stage1_analyze_images(module_id, image_logger)
            prd_content, prd_file = image_service._stage2_generate_prd(module_id, analyses, image_logger)
            image_service._update_module(module_id, prd_final_content=prd_content, status="completed", progress=100)

            metadata = _document_metadata_from_payload(
                {
                    "doc_id": module_id,
                    "title": title,
                    "product": request.form.get("product"),
                    "version": request.form.get("version"),
                    "module": request.form.get("module") or title,
                    "change_type": request.form.get("change_type"),
                },
                source_prefix="kb_image",
            )
            result = _clean_hint_and_import_prd(
                prd_content=prd_content,
                metadata=metadata,
                import_cleaned_json=import_cleaned_json_path,
                rebuild=True,
            )
            result["image_module_id"] = module_id
            result["image_upload"] = upload_result
            result["prd_file"] = prd_file
            return success_response(result)
        except Exception as exc:
            return error_response(f"导入图片 PRD 到知识库失败: {exc}", 500)

    @app.route("/api/kb/v1/documents/import-image-module", methods=["POST"])
    def import_existing_image_module_to_kb():
        try:
            data = request.get_json(silent=True) or {}
            module_id = str(data.get("module_id") or "").strip()
            if not module_id:
                return error_response("缺少必要参数: module_id", 400)
            result = _generate_module_prd_and_import(
                module_id=module_id,
                metadata_overrides=data,
                import_cleaned_json=import_cleaned_json_path,
            )
            return success_response(result)
        except Exception as exc:
            return error_response(f"导入图片模块到知识库失败: {exc}", 500)

    @app.route("/api/kb/v1/stats", methods=["GET"])
    def kb_stats():
        try:
            return success_response(light_unit_kb().stats())
        except Exception as exc:
            return error_response(f"获取知识库统计失败: {exc}", 500)

    @app.route("/api/kb/v1/documents", methods=["GET"])
    def list_kb_documents():
        try:
            return success_response({"documents": light_unit_kb().list_documents()})
        except Exception as exc:
            return error_response(f"获取知识库文档失败: {exc}", 500)

    @app.route("/api/kb/v1/documents/<doc_id>/units", methods=["GET"])
    def list_kb_document_units(doc_id):
        try:
            return success_response({"units": light_unit_kb().get_units(doc_id)})
        except Exception as exc:
            return error_response(f"获取知识单元失败: {exc}", 500)

    @app.route("/api/kb/v1/retrieval/search", methods=["POST"])
    def search_kb_units():
        try:
            data = request.get_json(silent=True) or {}
            query = str(data.get("query") or "").strip()
            if not query:
                return error_response("缺少必要参数: query", 400)
            results = semantic_unit_kb(judge="rule").search(
                query=query,
                top_k=int(data.get("top_k") or 5),
                product=data.get("product"),
                version=data.get("version"),
                vector_types=_optional_string_list(data.get("vector_types")),
                candidate_k=_optional_int(data.get("candidate_k")),
                evidence_k=_optional_int(data.get("evidence_k")),
                module=data.get("module"),
                min_score=_optional_float(data.get("min_score")),
            )
            return success_response({"query": query, "results": results})
        except Exception as exc:
            return error_response(f"搜索知识单元失败: {exc}", 500)

    @app.route("/api/kb/v1/retrieval/ask", methods=["POST"])
    def ask_kb_units():
        try:
            data = request.get_json(silent=True) or {}
            question = str(data.get("question") or data.get("query") or "").strip()
            if not question:
                return error_response("缺少必要参数: question", 400)
            judge = str(data.get("judge") or "llm").strip().lower()
            if judge not in {"llm", "rule"}:
                return error_response("judge 只能是 llm 或 rule", 400)
            result = semantic_unit_kb(judge=judge).ask(
                question,
                top_k=int(data.get("top_k") or 5),
                product=data.get("product"),
                version=data.get("version"),
            )
            return success_response(result)
        except Exception as exc:
            return error_response(f"知识库问答失败: {exc}", 500)

    @app.route("/api/kb/v1/retrieval/agent-ask", methods=["POST"])
    def agent_ask_kb_units():
        audit_id = uuid.uuid4().hex
        started_at = time.time()
        data = {}
        question = ""
        try:
            data = request.get_json(silent=True) or {}
            question = str(data.get("question") or data.get("query") or "").strip()
            if not question:
                return error_response("缺少必要参数: question", 400)
            result = mcp_qa_agent().answer(
                question,
                product=data.get("product"),
                version=data.get("version"),
                top_k_hint=int(data.get("top_k")) if data.get("top_k") else None,
            )
            result["audit_id"] = audit_id
            _append_agent_ask_audit({
                "audit_id": audit_id,
                "created_at": datetime.utcnow().isoformat(),
                "status": "success",
                "duration_seconds": round(time.time() - started_at, 3),
                "question": question,
                "product": data.get("product"),
                "version": data.get("version"),
                "top_k_hint": data.get("top_k"),
                "answerable": result.get("answerable"),
                "answer": result.get("answer"),
                "reason": result.get("reason"),
                "sources": result.get("sources") or [],
                "tool_trace": result.get("tool_trace") or [],
                "backend_tool_trace": result.get("backend_tool_trace") or result.get("tool_trace") or [],
                "model_call_trace": result.get("model_call_trace") or [],
                "model": result.get("model"),
                "usage": result.get("usage"),
                "usage_stats": result.get("usage_stats") or {},
                "raw_final": result.get("raw_final"),
            })
            return success_response(result)
        except Exception as exc:
            _append_agent_ask_audit({
                "audit_id": audit_id,
                "created_at": datetime.utcnow().isoformat(),
                "status": "error",
                "duration_seconds": round(time.time() - started_at, 3),
                "question": question,
                "product": data.get("product") if isinstance(data, dict) else None,
                "version": data.get("version") if isinstance(data, dict) else None,
                "top_k_hint": data.get("top_k") if isinstance(data, dict) else None,
                "error": str(exc),
            })
            return error_response(f"MCP Agent 知识库问答失败: {exc}", 500)

    @app.route("/api/kb/v1/retrieval/agent-ask/audits", methods=["GET"])
    def list_agent_ask_audits():
        try:
            limit = int(request.args.get("limit") or 20)
            return success_response({"audits": _read_agent_ask_audits(limit=limit)})
        except Exception as exc:
            return error_response(f"读取 MCP Agent 审计日志失败: {exc}", 500)

    @app.route("/api/kb/v1/feedback/query-hints", methods=["POST"])
    def add_kb_query_hint_feedback():
        try:
            data = request.get_json(silent=True) or {}
            doc_id = str(data.get("doc_id") or "").strip()
            unit_id = str(data.get("unit_id") or "").strip()
            query_text = str(data.get("query") or data.get("query_text") or "").strip()
            if not doc_id or not unit_id or not query_text:
                return error_response("缺少必要参数: doc_id, unit_id, query", 400)
            result = semantic_unit_kb(judge="rule").add_feedback_hint(doc_id, unit_id, query_text)
            return success_response(result)
        except Exception as exc:
            return error_response(f"添加反馈问法失败: {exc}", 500)


def _optional_string_list(value):
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item or "").strip()]
        return items or None
    text = str(value).strip()
    return [text] if text else None


def _optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kb_store_cache_key(judge, *, lightweight):
    return (
        os.environ.get("KB_STORAGE_MODE", "enterprise"),
        os.environ.get("PRD_UNIT_KB_DB", DEFAULT_DB_PATH),
        os.environ.get("KB_POSTGRES_DSN", ""),
        os.environ.get("KB_QDRANT_URL", ""),
        os.environ.get("KB_QDRANT_COLLECTION", ""),
        os.environ.get("PRD_UNIT_EMBEDDING_PROVIDER", "sentence"),
        os.environ.get("PRD_UNIT_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        str(judge or "rule").strip().lower(),
        "light" if lightweight else "semantic",
    )


def _append_agent_ask_audit(record):
    audit_path = Path(os.environ.get("KB_AGENT_AUDIT_LOG", KB_AGENT_AUDIT_LOG))
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str))
        file.write("\n")


def _read_agent_ask_audits(limit=20):
    audit_path = Path(os.environ.get("KB_AGENT_AUDIT_LOG", KB_AGENT_AUDIT_LOG))
    if not audit_path.exists():
        return []
    safe_limit = min(max(int(limit or 20), 1), 200)
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines[-safe_limit:]):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"status": "parse_error", "raw": line})
    return records


def _document_metadata_from_payload(data, source_prefix):
    now_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    title = str(data.get("title") or data.get("name") or f"知识文档_{now_id}").strip()
    doc_id = str(data.get("doc_id") or "").strip()
    if not doc_id:
        doc_id = f"{source_prefix}_{now_id}_{_safe_slug(title)[:32]}"
    return {
        "doc_id": doc_id,
        "title": title,
        "product": str(data.get("product") or "unknown").strip() or "unknown",
        "version": str(data.get("version") or "unknown").strip() or "unknown",
        "module": str(data.get("module") or title).strip() or title,
        "change_type": str(data.get("change_type") or "unknown").strip() or "unknown",
    }


def _clean_hint_and_import_prd(*, prd_content, metadata, import_cleaned_json, rebuild):
    from services.generation.prd_document_cleaner import clean_prd_document
    from services.kb.prd_cleaning_agent import PRDCleaningAgent
    from services.kb.prd_query_hint_agent import PRDQueryHintAgent, augment_cleaned_with_query_hints

    output_dir = Path(KB_IMPORT_OUTPUT_DIR) / _safe_slug(metadata["doc_id"])
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized_prd = clean_prd_document(prd_content)
    source_path = output_dir / "source.md"
    source_path.write_text(normalized_prd, encoding="utf-8")

    cleaning_agent = PRDCleaningAgent()
    cleaned = cleaning_agent.clean(document=metadata, prd_content=normalized_prd)
    cleaned_path = output_dir / "cleaned.json"
    cleaned_path.write_text(json.dumps(_without_private_agent_fields(cleaned), ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "cleaning.prompt.txt").write_text(cleaned.get("_prompt") or "", encoding="utf-8")
    (output_dir / "cleaning.raw_response.txt").write_text(cleaned.get("_raw_response") or "", encoding="utf-8")

    hint_agent = PRDQueryHintAgent()
    hint_result = hint_agent.generate(cleaned=cleaned)
    with_hints = augment_cleaned_with_query_hints(_without_private_agent_fields(cleaned), hint_result)
    with_hints_path = output_dir / "with_hints.json"
    with_hints_path.write_text(json.dumps(with_hints, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "query_hints.json").write_text(
        json.dumps(_without_private_agent_fields(hint_result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "query_hints.prompt.txt").write_text(hint_result.get("_prompt") or "", encoding="utf-8")
    (output_dir / "query_hints.raw_response.txt").write_text(hint_result.get("_raw_response") or "", encoding="utf-8")

    import_result = import_cleaned_json(str(with_hints_path), rebuild=rebuild)
    return {
        "doc_id": metadata["doc_id"],
        "title": metadata["title"],
        "prd_content": normalized_prd,
        "source_path": str(source_path),
        "cleaned_json": str(cleaned_path),
        "with_hints_json": str(with_hints_path),
        "unit_count": len(with_hints.get("units") or []),
        "import_result": import_result,
    }


def _generate_module_prd_and_import(*, module_id, metadata_overrides, import_cleaned_json):
    from services.generation.image_pipeline_service import ImagePipelineService

    image_service = ImagePipelineService()
    module = image_service._get_module(module_id)
    if not module:
        raise ValueError(f"需求模块不存在: {module_id}")
    if not module.images:
        raise ValueError("需求模块没有上传图片")

    image_logger = _NoopPipelineLogger()
    analyses = image_service._stage1_analyze_images(module_id, image_logger)
    prd_content, prd_file = image_service._stage2_generate_prd(module_id, analyses, image_logger)
    image_service._update_module(module_id, prd_final_content=prd_content, status="completed", progress=100)

    metadata = _document_metadata_from_payload(
        {
            "doc_id": module_id,
            "title": metadata_overrides.get("title") or module.name,
            "product": metadata_overrides.get("product"),
            "version": metadata_overrides.get("version"),
            "module": metadata_overrides.get("module") or module.name,
            "change_type": metadata_overrides.get("change_type"),
        },
        source_prefix="kb_image",
    )
    result = _clean_hint_and_import_prd(
        prd_content=prd_content,
        metadata=metadata,
        import_cleaned_json=import_cleaned_json,
        rebuild=True,
    )
    result["image_module_id"] = module_id
    result["prd_file"] = prd_file
    return result


def _without_private_agent_fields(value):
    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if not key.startswith("_")}


def _safe_slug(value):
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(value or "document"))
    return text.strip("_") or "document"


class _NoopStageLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _NoopPipelineLogger:
    def __init__(self):
        self.stage_loggers = {
            "stage1": _NoopStageLogger(),
            "stage2": _NoopStageLogger(),
            "stage3": _NoopStageLogger(),
            "stage5": _NoopStageLogger(),
        }

    def log_performance_metric(self, *args, **kwargs):
        pass

    def save_ai_response(self, *args, **kwargs):
        pass
