"""LLM-backed query hint generator for cleaned PRD requirement units."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agents.qa_agents.model_selector import get_models_by_type
from agents.qa_agents.templates.prd_query_hint_generator import (
    SCHEMA_VERSION,
    TEMPLATES as QUERY_HINT_TEMPLATES,
)
from config import Config
from services.generation.llm_json_parser import parse_llm_json
from services.generation.llm_response_cleaner import strip_model_reasoning


@dataclass
class QueryHintModelConfig:
    model: str
    api_key: str
    base_url: str


class PRDQueryHintAgent:
    """Generate retrieval metadata for cleaned requirement units."""

    def __init__(
        self,
        config_list: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[QueryHintModelConfig] = None,
        timeout: int = 600,
        max_query_hints: int = 4,
        max_key_terms: int = 12,
    ):
        self.config_list = config_list
        self.model_config = model_config
        self.timeout = timeout
        self.max_query_hints = max(1, max_query_hints)
        self.max_key_terms = max(1, max_key_terms)
        self.system_message = QUERY_HINT_TEMPLATES["需求问法提示生成"]["system_message"]

    def generate(
        self,
        *,
        cleaned: Dict[str, Any],
        unit_ids: Optional[List[str]] = None,
        max_units: Optional[int] = None,
    ) -> Dict[str, Any]:
        document = cleaned.get("document") or {}
        units = select_units(cleaned.get("units") or [], unit_ids=unit_ids, max_units=max_units)
        if not units:
            raise ValueError("No units selected for query hint generation")

        prompt = build_query_hint_prompt(document, units)
        started_at = time.time()
        raw_response, model_meta = self._call_model(prompt)
        duration = round(time.time() - started_at, 3)

        parsed = parse_llm_json(raw_response)
        normalized = normalize_query_hint_output(
            parsed,
            document=document,
            source_units=units,
            max_query_hints=self.max_query_hints,
            max_key_terms=self.max_key_terms,
        )
        issues = validate_query_hint_output(normalized)
        normalized["metrics"] = {
            "duration_seconds": duration,
            "prompt_chars": len(prompt),
            "response_chars": len(raw_response or ""),
            "unit_count": len(normalized.get("units") or []),
            "model": model_meta.get("model"),
            "usage": model_meta.get("usage"),
            "validation_issue_count": len(issues),
            "validation_issues": issues,
            "tested_at": datetime.utcnow().isoformat(),
        }
        normalized["_prompt"] = prompt
        normalized["_raw_response"] = raw_response
        return normalized

    def _call_model(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
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

    def _resolve_model_config(self) -> QueryHintModelConfig:
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
        return QueryHintModelConfig(model=model, api_key=api_key, base_url=base_url)


def build_query_hint_prompt(document: Dict[str, Any], units: List[Dict[str, Any]]) -> str:
    metadata = {
        "doc_id": document.get("doc_id") or "",
        "title": document.get("title") or "",
        "product": document.get("product") or "",
        "version": document.get("version") or "",
        "module": document.get("module") or "",
    }
    compact_units = []
    for unit in units:
        compact_units.append({
            "unit_id": unit.get("unit_id") or "",
            "title": unit.get("title") or "",
            "unit_type": unit.get("unit_type") or "",
            "content": unit.get("content") or "",
            "rules": unit.get("rules") or [],
        })

    return f"""请为以下知识单元生成 query_hints 和 key_terms，输出符合 schema 的 JSON。

【文档元信息】
{json.dumps(metadata, ensure_ascii=False, indent=2)}

【输出要求补充】
- schema_version 必须是 {SCHEMA_VERSION}
- 必须为输入中的每个 unit_id 输出一条结果。
- query_hints 每个 unit 建议 2-5 条，不能引入原文没有的新功能。
- key_terms 必须来自 unit.title/content/rules 的原文表达，优先保留按钮、提示文案、数值、否定项。
- key_terms 不要输出泛词，例如“功能”“系统”“用户”“数据”。

【知识单元】
{json.dumps(compact_units, ensure_ascii=False, indent=2)}
"""


def select_units(
    units: List[Dict[str, Any]],
    *,
    unit_ids: Optional[List[str]] = None,
    max_units: Optional[int] = None,
) -> List[Dict[str, Any]]:
    selected = list(units)
    if unit_ids:
        wanted = {str(unit_id).strip() for unit_id in unit_ids if str(unit_id).strip()}
        selected = [unit for unit in selected if str(unit.get("unit_id") or "").strip() in wanted]
    if max_units:
        selected = selected[:max(0, max_units)]
    return selected


def normalize_query_hint_output(
    parsed: Any,
    *,
    document: Dict[str, Any],
    source_units: List[Dict[str, Any]],
    max_query_hints: int = 5,
    max_key_terms: int = 12,
) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("query hint response must be a JSON object")

    generated_by_id = {}
    for item in _as_list(parsed.get("units")):
        if isinstance(item, dict):
            unit_id = str(item.get("unit_id") or "").strip()
            if unit_id:
                generated_by_id[unit_id] = item

    normalized_units = []
    warnings: List[str] = _as_string_list(parsed.get("warnings"))
    for source_unit in source_units:
        unit_id = str(source_unit.get("unit_id") or "").strip()
        generated = generated_by_id.get(unit_id, {})
        if not generated:
            warnings.append(f"{unit_id} missing from query hint response")

        query_hints = _normalize_query_hints(generated.get("query_hints"), max_query_hints=max_query_hints)
        key_terms, dropped_terms = _normalize_key_terms(
            generated.get("key_terms"),
            source_unit=source_unit,
            max_key_terms=max_key_terms,
        )
        for term in dropped_terms:
            warnings.append(f"{unit_id} dropped key_term not found in source: {term}")

        if not key_terms:
            key_terms = extract_key_terms_from_unit(source_unit, max_key_terms=max_key_terms)

        hint_unit = {
            "unit_id": unit_id,
            "query_hints": query_hints,
            "key_terms": key_terms,
        }
        hint_unit["hint_embedding_text"] = build_query_hint_embedding_text(document, source_unit, hint_unit)
        hint_unit["source_content_hash"] = str(source_unit.get("content_hash") or _content_hash(source_unit))
        normalized_units.append(hint_unit)

    doc = parsed.get("document") if isinstance(parsed.get("document"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "document": {
            "doc_id": str(doc.get("doc_id") or document.get("doc_id") or "").strip(),
            "title": str(doc.get("title") or document.get("title") or "").strip(),
        },
        "units": normalized_units,
        "warnings": warnings,
    }


def validate_query_hint_output(result: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    units = result.get("units") or []
    if not units:
        issues.append("units is empty")
    seen = set()
    for index, unit in enumerate(units, 1):
        unit_id = unit.get("unit_id") or f"index:{index}"
        if unit_id in seen:
            issues.append(f"duplicate unit_id: {unit_id}")
        seen.add(unit_id)
        if not unit.get("query_hints"):
            issues.append(f"{unit_id} query_hints is empty")
        if not unit.get("key_terms"):
            issues.append(f"{unit_id} key_terms is empty")
    return issues


def augment_cleaned_with_query_hints(cleaned: Dict[str, Any], hint_result: Dict[str, Any]) -> Dict[str, Any]:
    augmented = deepcopy(cleaned)
    hints_by_id = {
        str(unit.get("unit_id") or ""): unit
        for unit in hint_result.get("units") or []
        if isinstance(unit, dict)
    }
    for unit in augmented.get("units") or []:
        unit_id = str(unit.get("unit_id") or "")
        hint_unit = hints_by_id.get(unit_id)
        if not hint_unit:
            continue
        unit["retrieval_meta"] = {
            "query_hints": list(hint_unit.get("query_hints") or []),
            "key_terms": list(hint_unit.get("key_terms") or []),
        }
        unit["query_hints_embedding_text"] = hint_unit.get("hint_embedding_text") or ""
    return augmented


def build_query_hint_embedding_text(
    document: Dict[str, Any],
    source_unit: Dict[str, Any],
    hint_unit: Dict[str, Any],
) -> str:
    lines = [
        f"产品：{document.get('product') or 'unknown'}",
        f"版本：{document.get('version') or 'unknown'}",
        f"模块：{document.get('module') or 'unknown'}",
        f"需求：{document.get('title') or 'unknown'}",
        f"知识单元：{source_unit.get('title') or 'unknown'}",
        "用户可能问：",
    ]
    lines.extend(f"- {hint}" for hint in hint_unit.get("query_hints") or [])
    key_terms = hint_unit.get("key_terms") or []
    if key_terms:
        lines.append("关键证据词：")
        lines.extend(f"- {term}" for term in key_terms)
    return "\n".join(lines).strip()


def extract_key_terms_from_unit(source_unit: Dict[str, Any], max_key_terms: int = 12) -> List[str]:
    source_text = _unit_source_text(source_unit)
    candidates: List[str] = []
    candidates.extend(_quoted_phrases(source_text))
    candidates.extend(re.findall(r"\d+(?:\.\d+)?\s*(?:分钟|小时|天|个月|米|倍|x|X|%)", source_text))
    title = _clean_inline(source_unit.get("title") or "")
    if 2 <= len(title) <= 28:
        candidates.append(title)
    return _dedupe_strings(candidates, max_items=max_key_terms)


def _normalize_query_hints(value: Any, *, max_query_hints: int) -> List[str]:
    hints = []
    for item in _as_list(value):
        text = _clean_inline(item)
        if not text:
            continue
        text = text[:120].strip()
        hints.append(text)
    return _dedupe_strings(hints, max_items=max_query_hints)


def _normalize_key_terms(
    value: Any,
    *,
    source_unit: Dict[str, Any],
    max_key_terms: int,
) -> Tuple[List[str], List[str]]:
    source_text = _unit_source_text(source_unit)
    kept: List[str] = []
    dropped: List[str] = []
    for item in _as_list(value):
        term = _clean_inline(item)
        if not term or _is_generic_term(term):
            continue
        term = term[:80].strip()
        if _contains_term(source_text, term):
            kept.append(term)
        else:
            dropped.append(term)

    fallback = extract_key_terms_from_unit(source_unit, max_key_terms=max_key_terms)
    kept.extend(term for term in fallback if term not in kept)
    return _dedupe_strings(kept, max_items=max_key_terms), _dedupe_strings(dropped, max_items=max_key_terms)


def _unit_source_text(unit: Dict[str, Any]) -> str:
    parts = [
        str(unit.get("title") or ""),
        str(unit.get("content") or ""),
    ]
    parts.extend(str(rule or "") for rule in unit.get("rules") or [])
    return "\n".join(parts)


def _contains_term(source_text: str, term: str) -> bool:
    compact_source = _compact_for_match(source_text)
    compact_term = _compact_for_match(term)
    return bool(compact_term and compact_term in compact_source)


def _compact_for_match(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("“", "\"").replace("”", "\"").replace("「", "\"").replace("」", "\"")
    return text


def _quoted_phrases(text: str) -> List[str]:
    phrases: List[str] = []
    for pattern in [r"「([^」]{2,60})」", r"“([^”]{2,60})”", r"\"([^\"]{2,60})\""]:
        phrases.extend(match.strip() for match in re.findall(pattern, text) if match.strip())
    return phrases


def _is_generic_term(term: str) -> bool:
    return term in {"功能", "系统", "用户", "数据", "页面", "信息", "操作", "规则", "需求", "...", "……"}


def _dedupe_strings(values: List[str], *, max_items: int) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _clean_inline(value)
        key = _compact_for_match(text).lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
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


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
