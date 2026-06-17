"""DeepSeek-backed PRD cleaning agent for vector-ready requirement units."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agents.qa_agents.templates.prd_kb_cleaner import SCHEMA_VERSION, TEMPLATES as CLEANER_TEMPLATES
from agents.qa_agents.model_selector import get_models_by_type
from config import Config
from services.generation.llm_json_parser import parse_llm_json
from services.generation.llm_response_cleaner import strip_model_reasoning


ALLOWED_UNIT_TYPES = {
    "feature",
    "business_rule",
    "flow",
    "data",
    "permission",
    "exception",
    "non_functional",
    "other",
}


@dataclass
class CleaningModelConfig:
    model: str
    api_key: str
    base_url: str


class PRDCleaningAgent:
    """Clean final PRDs into lightweight requirement units."""

    def __init__(
        self,
        config_list: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[CleaningModelConfig] = None,
        timeout: int = 600,
    ):
        self.config_list = config_list
        self.model_config = model_config
        self.timeout = timeout
        self.system_message = CLEANER_TEMPLATES["轻量知识单元清洗"]["system_message"]

    def clean(
        self,
        *,
        document: Dict[str, Any],
        prd_content: str,
        max_source_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        source_text = str(prd_content or "").strip()
        if not source_text:
            raise ValueError("prd_content is empty")

        if max_source_chars and len(source_text) > max_source_chars:
            source_text = source_text[:max_source_chars].rstrip()
            source_text += "\n\n[TRUNCATED_FOR_CLEANING_TEST]"

        prompt = build_cleaning_prompt(document, source_text)
        started_at = time.time()
        raw_response, model_meta = self._call_deepseek(prompt)
        duration = round(time.time() - started_at, 3)

        parsed = parse_llm_json(raw_response)
        cleaned = normalize_cleaning_output(parsed, document)
        validation_issues = validate_cleaning_output(cleaned)
        cleaned["metrics"] = {
            "duration_seconds": duration,
            "source_chars": len(source_text),
            "prompt_chars": len(prompt),
            "response_chars": len(raw_response or ""),
            "unit_count": len(cleaned.get("units") or []),
            "model": model_meta.get("model"),
            "usage": model_meta.get("usage"),
            "validation_issue_count": len(validation_issues),
            "validation_issues": validation_issues,
            "tested_at": datetime.utcnow().isoformat(),
        }
        cleaned["_prompt"] = prompt
        cleaned["_raw_response"] = raw_response
        return cleaned

    def _call_deepseek(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        config = self._resolve_model_config()
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": config.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": prompt},
            ],
        }
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response has no choices")
        message = choices[0].get("message") or {}
        content = strip_model_reasoning(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM response content is empty")
        return content, {
            "model": data.get("model") or config.model,
            "usage": data.get("usage"),
        }

    def _resolve_model_config(self) -> CleaningModelConfig:
        if self.model_config:
            return self.model_config

        config_list = self.config_list
        if config_list is None:
            config_list = Config().load_config() or []
        text_configs = get_models_by_type(config_list, model_type="text")
        if not text_configs:
            raise RuntimeError("No text model config found")

        cfg = text_configs[0]
        model = str(cfg.get("model") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "").strip()
        if not model or not api_key or not base_url:
            raise RuntimeError("Text model config requires model, api_key and base_url")
        return CleaningModelConfig(model=model, api_key=api_key, base_url=base_url)


def build_cleaning_prompt(document: Dict[str, Any], prd_content: str) -> str:
    metadata = {
        "doc_id": document.get("doc_id") or document.get("id") or "",
        "title": document.get("title") or document.get("name") or "",
        "product": document.get("product") or "unknown",
        "version": document.get("version") or "unknown",
        "module": document.get("module") or "unknown",
        "change_type": document.get("change_type") or "unknown",
    }
    numbered = _numbered_lines(prd_content)
    return f"""请清洗以下知识库源文档，输出符合 schema 的 JSON。

【文档元信息】
{json.dumps(metadata, ensure_ascii=False, indent=2)}

【输出要求补充】
- schema_version 必须是 {SCHEMA_VERSION}
- document 必须沿用文档元信息，不要改写 doc_id/version。
- unit_id 使用 RU-001 起递增。
- rules 只放字符串数组，禁止输出复杂嵌套对象。
- source.start_line/source.end_line 必须引用下面带行号原文中的真实行号。
- 不要输出 evidence 字段。
- content 写业务对象、动作和关键结果；rules 逐条保留按钮名、字段名、toast、数值、状态、示例、否定规则、页面动作和布局细节。
- 不要泛化精确名称，例如不要把“去词库中添加词条”写成“右上角按钮”。

【带行号知识库源文档】
{numbered}
"""


def normalize_cleaning_output(parsed: Any, document: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("cleaning response must be a JSON object")

    doc = parsed.get("document") if isinstance(parsed.get("document"), dict) else {}
    normalized_doc = {
        "doc_id": str(doc.get("doc_id") or document.get("doc_id") or document.get("id") or "").strip(),
        "title": str(doc.get("title") or document.get("title") or document.get("name") or "").strip(),
        "product": str(doc.get("product") or document.get("product") or "unknown").strip(),
        "version": str(doc.get("version") or document.get("version") or "unknown").strip(),
        "module": str(doc.get("module") or document.get("module") or "unknown").strip(),
        "change_type": str(doc.get("change_type") or document.get("change_type") or "unknown").strip(),
        "summary": _clean_inline(doc.get("summary") or ""),
    }

    units = parsed.get("units") or parsed.get("requirement_units") or []
    normalized_units = []
    for index, item in enumerate(_as_list(units), 1):
        if not isinstance(item, dict):
            continue
        unit = {
            "unit_id": _normalize_unit_id(item.get("unit_id"), index),
            "title": _clean_inline(item.get("title") or f"知识单元 {index}"),
            "unit_type": _normalize_unit_type(item.get("unit_type")),
            "content": _clean_text(item.get("content") or item.get("summary") or ""),
            "rules": [_clean_inline(value) for value in _rule_strings(item.get("rules")) if _clean_inline(value)],
            "source": _normalize_source(item.get("source")),
        }
        unit["embedding_text"] = build_requirement_unit_embedding_text(normalized_doc, unit)
        unit["content_hash"] = _content_hash({
            "schema_version": SCHEMA_VERSION,
            "document": normalized_doc,
            "unit": {key: value for key, value in unit.items() if key not in {"embedding_text", "content_hash"}},
        })
        normalized_units.append(unit)

    return {
        "schema_version": SCHEMA_VERSION,
        "document": normalized_doc,
        "units": normalized_units,
        "warnings": _as_string_list(parsed.get("warnings")),
    }


def validate_cleaning_output(cleaned: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    doc = cleaned.get("document") or {}
    if not doc.get("doc_id"):
        issues.append("document.doc_id is empty")
    if not doc.get("title"):
        issues.append("document.title is empty")

    units = cleaned.get("units") or []
    if not units:
        issues.append("units is empty")
    seen_ids = set()
    for index, unit in enumerate(units, 1):
        unit_id = unit.get("unit_id") or f"index:{index}"
        if unit_id in seen_ids:
            issues.append(f"duplicate unit_id: {unit_id}")
        seen_ids.add(unit_id)
        if not unit.get("title"):
            issues.append(f"{unit_id} title is empty")
        if not unit.get("content"):
            issues.append(f"{unit_id} content is empty")
        if len(str(unit.get("content") or "")) > 900:
            issues.append(f"{unit_id} content is long: {len(str(unit.get('content') or ''))} chars")
        source = unit.get("source") or {}
        if not source.get("start_line") or not source.get("end_line"):
            issues.append(f"{unit_id} source line range is missing")
        elif int(source["start_line"]) > int(source["end_line"]):
            issues.append(f"{unit_id} source line range is invalid")
    return issues


def build_requirement_unit_embedding_text(document: Dict[str, Any], unit: Dict[str, Any]) -> str:
    source = unit.get("source") or {}
    lines = [
        f"产品：{document.get('product') or 'unknown'}",
        f"版本：{document.get('version') or 'unknown'}",
        f"模块：{document.get('module') or 'unknown'}",
        f"需求：{document.get('title') or 'unknown'}",
        f"知识单元：{unit.get('title') or 'unknown'}",
        f"类型：{unit.get('unit_type') or 'other'}",
        f"章节：{' > '.join(source.get('heading_path') or [])}",
        "内容：",
        str(unit.get("content") or "").strip(),
    ]
    rules = unit.get("rules") or []
    if rules:
        lines.append("规则：")
        lines.extend(f"- {rule}" for rule in rules)
    return "\n".join(line for line in lines if line is not None).strip()


def build_document_metadata(module: Dict[str, Any], prd_content: str) -> Dict[str, str]:
    name = str(module.get("name") or module.get("title") or "").strip()
    text = f"{name}\n{str(prd_content or '')[:1200]}"
    version_match = re.search(r"[vV]?\d+(?:\.\d+){1,3}", text)
    version = version_match.group(0) if version_match else "unknown"
    product = str(module.get("product") or module.get("business") or "unknown").strip() or "unknown"
    value = name
    if version != "unknown":
        value = value.replace(version, "").replace(version.lower(), "").replace(version.upper(), "")
    module_name = re.sub(r"[_\s-]+", " ", value).strip()
    return {
        "doc_id": str(module.get("id") or module.get("doc_id") or "").strip(),
        "title": name,
        "product": product,
        "version": version,
        "module": module_name or "unknown",
        "change_type": _extract_change_type(text),
    }


def _extract_change_type(text: str) -> str:
    normalized = re.sub(r"[*`_]", "", str(text or ""))
    match = re.search(r"(?:变更类型|版本类型)\s*[：:]\s*([^\n|]+)", normalized)
    if not match:
        return "unknown"
    value = re.sub(r"\s+", "", match.group(1)).strip()
    return value or "unknown"


def _numbered_lines(text: str) -> str:
    return "\n".join(f"{index:04d}: {line}" for index, line in enumerate(str(text or "").splitlines(), 1))


def _normalize_unit_id(value: Any, index: int) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"RU-\d{3}", text):
        return text
    return f"RU-{index:03d}"


def _normalize_unit_type(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in ALLOWED_UNIT_TYPES else "other"


def _normalize_source(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "heading_path": _as_string_list(source.get("heading_path")),
        "start_line": _to_positive_int(source.get("start_line")),
        "end_line": _to_positive_int(source.get("end_line")),
    }


def _rule_strings(value: Any) -> List[str]:
    result: List[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            parts = [
                _clean_inline(item.get("condition") or ""),
                _clean_inline(item.get("behavior") or item.get("result") or ""),
                _clean_inline(item.get("message") or ""),
            ]
            text = "；".join(part for part in parts if part)
        else:
            text = _clean_inline(item)
        if text:
            result.append(text)
    return result


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_string_list(value: Any) -> List[str]:
    return [str(item).strip() for item in _as_list(value) if str(item or "").strip()]


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _to_positive_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
