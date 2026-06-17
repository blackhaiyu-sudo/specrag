"""Rule-based answerability gate for PRD requirement-unit retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from services.generation.llm_json_parser import parse_llm_json
from services.generation.llm_response_cleaner import strip_model_reasoning


ANSWER_INTENTS: List[Dict[str, Any]] = [
    {
        "name": "frequency",
        "query_patterns": [r"频率", r"实时", r"(采集|同步|刷新|上报).*间隔", r"多久.*(采集|同步|刷新|上报)", r"每\d"],
        "evidence_patterns": [
            r"采集频率",
            r"上报频率",
            r"同步频率",
            r"刷新频率",
            r"(采集|上报|同步|刷新).{0,8}间隔",
            r"每\d+\s*(秒|分钟|小时)",
            r"\d+\s*(秒|分钟|小时)\s*一次",
        ],
    },
    {
        "name": "export",
        "query_patterns": [r"导出", r"Excel", r"下载"],
        "evidence_patterns": [r"导出", r"Excel", r"下载", r"导出文件", r"报表"],
    },
    {
        "name": "delete",
        "query_patterns": [r"删除", r"清除", r"移除", r"保留策略"],
        "evidence_patterns": [r"删除", r"清除", r"移除", r"保留", r"保留策略", r"过期", r"销毁"],
    },
    {
        "name": "retention",
        "query_patterns": [r"保留多久", r"保存多久", r"存储多久", r"数据.*保留", r"数据.*保存"],
        "evidence_patterns": [r"保留多久", r"保存多久", r"存储多久", r"保留策略", r"保存策略", r"有效期", r"过期", r"自动清理"],
    },
    {
        "name": "permission",
        "query_patterns": [r"权限", r"角色", r"谁可以", r"谁能", r"哪些人"],
        "evidence_patterns": [r"权限", r"角色", r"管理员", r"调度员", r"可见", r"授权", r"允许"],
    },
    {
        "name": "share",
        "query_patterns": [r"分享", r"转发", r"发送给", r"共享"],
        "evidence_patterns": [r"分享", r"转发", r"共享", r"发送给"],
    },
    {
        "name": "prompt",
        "query_patterns": [r"提示什么", r"怎么提示", r"提示"],
        "evidence_patterns": [r"提示", r"Toast", r"请", r"重新选择", r"不能", r"至少"],
    },
    {
        "name": "duration_or_time_range",
        "query_patterns": [r"多久", r"多长时间", r"几天", r"几个月", r"以前"],
        "evidence_patterns": [r"\d+\s*(分钟|小时|天|个月)", r"最多", r"最少", r"不可选", r"置灰"],
    },
    {
        "name": "color",
        "query_patterns": [r"颜色", r"什么色"],
        "evidence_patterns": [r"颜色", r"蓝色", r"深蓝色", r"#[0-9A-Fa-f]{6}"],
    },
    {
        "name": "speed",
        "query_patterns": [r"速度", r"速率", r"倍率", r"倍速", r"几倍"],
        "evidence_patterns": [r"速度", r"速率", r"倍率", r"倍速", r"\d+(?:\.\d+)?x", r"\d+(?:\.\d+)?倍"],
    },
    {
        "name": "location_or_entry",
        "query_patterns": [r"哪里", r"在哪里", r"入口", r"从哪", r"哪个页面"],
        "evidence_patterns": [r"入口", r"页面", r"菜单", r"按钮", r"位置", r"导航", r"路径"],
    },
    {
        "name": "abnormal",
        "query_patterns": [r"异常", r"错误", r"失败", r"超时", r"标记"],
        "evidence_patterns": [r"异常", r"错误", r"失败", r"超时", r"标记", r"不允许", r"不处理", r"不展示"],
    },
]


class PRDAnswerabilityGate:
    """Checks whether retrieved PRD units contain enough evidence to answer."""

    def __init__(self, intents: List[Dict[str, Any]] | None = None):
        self.intents = intents or ANSWER_INTENTS

    def judge(self, query: str, units: List[Dict[str, Any]]) -> Dict[str, Any]:
        intents = self.detect_intents(query)
        if not intents:
            return {
                "should_answer": True,
                "intents": [],
                "missing_intents": [],
                "evidence_hits": [],
                "reason": "no specific no-answer intent detected",
            }

        evidence_text = "\n".join(unit_evidence_text(unit) for unit in units)
        evidence_hits = []
        missing = []
        for intent in intents:
            terms = match_patterns(evidence_text, intent["evidence_patterns"])
            if terms:
                evidence_hits.append({"intent": intent["name"], "terms": terms})
            else:
                missing.append(intent["name"])

        return {
            "should_answer": not missing,
            "intents": [intent["name"] for intent in intents],
            "missing_intents": missing,
            "evidence_hits": evidence_hits,
        }

    def detect_intents(self, query: str) -> List[Dict[str, Any]]:
        return [intent for intent in self.intents if match_patterns(query, intent["query_patterns"])]


def judge_answerability(query: str, units: List[Dict[str, Any]]) -> Dict[str, Any]:
    return PRDAnswerabilityGate().judge(query, units)


@dataclass
class EvidenceJudgeModelConfig:
    model: str
    api_key: str
    base_url: str


class LLMEvidenceJudgeGate:
    """LLM-based evidence sufficiency judge for retrieved PRD units."""

    def __init__(
        self,
        config_list: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[EvidenceJudgeModelConfig] = None,
        timeout: int = 120,
    ):
        self.config_list = config_list
        self.model_config = model_config
        self.timeout = timeout
        template_module = _load_evidence_judge_template()
        self.system_message = template_module.TEMPLATES["证据充分性判断"]["system_message"]
        self._resolved_model_config: Optional[EvidenceJudgeModelConfig] = None

    def judge(self, query: str, units: List[Dict[str, Any]]) -> Dict[str, Any]:
        prompt = _load_evidence_judge_template().build_evidence_judge_prompt(query, units)
        started_at = time.time()
        raw_response, model_meta = self._call_model(prompt)
        parsed = parse_llm_json(raw_response)
        normalized = normalize_evidence_judge_output(parsed)
        normalized["judge_type"] = "llm_evidence"
        normalized["model"] = model_meta.get("model")
        normalized["usage"] = model_meta.get("usage")
        normalized["duration_seconds"] = round(time.time() - started_at, 3)
        return normalized

    def _call_model(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        config = self._resolve_model_config()
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": config.model,
            "temperature": 0,
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
            raise RuntimeError("LLM judge response has no choices")
        message = choices[0].get("message") or {}
        content = strip_model_reasoning(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM judge response content is empty")
        return content, {
            "model": data.get("model") or config.model,
            "usage": data.get("usage"),
        }

    def _resolve_model_config(self) -> EvidenceJudgeModelConfig:
        if self.model_config:
            return self.model_config
        if self._resolved_model_config:
            return self._resolved_model_config

        from agents.qa_agents.model_selector import get_models_by_type
        from config import Config

        config_list = self.config_list
        if config_list is None:
            config_list = Config().load_config() or []
        text_configs = get_models_by_type(config_list, model_type="text")
        if not text_configs:
            raise RuntimeError("No text model config found for evidence judge")

        cfg = text_configs[0]
        model = str(cfg.get("model") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "").strip()
        if not model or not api_key or not base_url:
            raise RuntimeError("Evidence judge model config requires model, api_key and base_url")
        self._resolved_model_config = EvidenceJudgeModelConfig(model=model, api_key=api_key, base_url=base_url)
        return self._resolved_model_config


class LLMEvidenceSynthesizerGate:
    """LLM-based answer synthesizer for multiple supporting PRD units."""

    def __init__(
        self,
        config_list: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[EvidenceJudgeModelConfig] = None,
        timeout: int = 120,
    ):
        self.config_list = config_list
        self.model_config = model_config
        self.timeout = timeout
        template_module = _load_evidence_judge_template()
        self.system_message = template_module.TEMPLATES["答案整合"]["system_message"]
        self._resolved_model_config: Optional[EvidenceJudgeModelConfig] = None

    def synthesize(self, query: str, units: List[Dict[str, Any]], answerability: Dict[str, Any]) -> Dict[str, Any]:
        prompt = _load_evidence_judge_template().build_answer_synthesis_prompt(query, units, answerability)
        started_at = time.time()
        raw_response, model_meta = self._call_model(prompt)
        parsed = parse_llm_json(raw_response)
        normalized = normalize_evidence_synthesis_output(parsed)
        normalized["judge_type"] = "llm_evidence_synthesis"
        normalized["model"] = model_meta.get("model")
        normalized["usage"] = model_meta.get("usage")
        normalized["duration_seconds"] = round(time.time() - started_at, 3)
        return normalized

    def _call_model(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        config = self._resolve_model_config()
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": config.model,
            "temperature": 0,
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
            raise RuntimeError("LLM synthesizer response has no choices")
        message = choices[0].get("message") or {}
        content = strip_model_reasoning(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM synthesizer response content is empty")
        return content, {
            "model": data.get("model") or config.model,
            "usage": data.get("usage"),
        }

    def _resolve_model_config(self) -> EvidenceJudgeModelConfig:
        if self.model_config:
            return self.model_config
        if self._resolved_model_config:
            return self._resolved_model_config

        from agents.qa_agents.model_selector import get_models_by_type
        from config import Config

        config_list = self.config_list
        if config_list is None:
            config_list = Config().load_config() or []
        text_configs = get_models_by_type(config_list, model_type="text")
        if not text_configs:
            raise RuntimeError("No text model config found for evidence synthesizer")

        cfg = text_configs[0]
        model = str(cfg.get("model") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "").strip()
        if not model or not api_key or not base_url:
            raise RuntimeError("Evidence synthesizer model config requires model, api_key and base_url")
        self._resolved_model_config = EvidenceJudgeModelConfig(model=model, api_key=api_key, base_url=base_url)
        return self._resolved_model_config


def normalize_evidence_judge_output(parsed: Any) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("LLM judge response must be a JSON object")

    should_answer = bool(parsed.get("should_answer"))
    supporting_unit_ids = _as_string_list(parsed.get("supporting_unit_ids"))
    missing_reason = str(parsed.get("missing_reason") or "").strip()
    unsafe_inference = str(parsed.get("unsafe_inference") or "").strip()

    if should_answer and not supporting_unit_ids:
        should_answer = False
        missing_reason = missing_reason or "judge did not provide supporting_unit_ids"

    return {
        "should_answer": should_answer,
        "supporting_unit_ids": supporting_unit_ids,
        "missing_reason": missing_reason,
        "unsafe_inference": unsafe_inference,
        "intents": [],
        "missing_intents": [] if should_answer else ["llm_evidence_insufficient"],
        "evidence_hits": [
            {"intent": "llm_evidence", "terms": supporting_unit_ids}
        ] if should_answer and supporting_unit_ids else [],
    }


def normalize_evidence_synthesis_output(parsed: Any) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("LLM synthesis response must be a JSON object")

    synthesized_answer = str(parsed.get("synthesized_answer") or "").strip()
    unsatisfied_points = _as_string_list(parsed.get("unsatisfied_points"))
    return {
        "synthesized_answer": synthesized_answer,
        "unsatisfied_points": unsatisfied_points,
    }


_EVIDENCE_JUDGE_TEMPLATE_MODULE = None


def _load_evidence_judge_template():
    global _EVIDENCE_JUDGE_TEMPLATE_MODULE
    if _EVIDENCE_JUDGE_TEMPLATE_MODULE is not None:
        return _EVIDENCE_JUDGE_TEMPLATE_MODULE

    root = Path(__file__).resolve().parents[2]
    template_path = root / "agents/qa_agents/templates/prd_evidence_judge.py"
    spec = importlib.util.spec_from_file_location("_prd_evidence_judge_template", template_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load evidence judge template: {template_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _EVIDENCE_JUDGE_TEMPLATE_MODULE = module
    return module


def match_patterns(text: str, patterns: List[str]) -> List[str]:
    hits: List[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits


def unit_evidence_text(unit: Dict[str, Any]) -> str:
    retrieval_meta = unit.get("retrieval_meta") or {}
    parts = [
        str(unit.get("title") or ""),
        str(unit.get("content") or ""),
    ]
    parts.extend(_string_items(unit.get("rules")))
    parts.extend(_extract_evidence_items(unit))
    parts.extend(_string_items(retrieval_meta.get("key_terms")))
    return "\n".join(item for item in parts if item)


def _extract_evidence_items(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"evidence", "evidences", "source_text", "source_excerpt", "quote"}:
                items.extend(_string_items(child))
            elif isinstance(child, (dict, list)):
                items.extend(_extract_evidence_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_extract_evidence_items(child))
    return items


def _string_items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        items: List[str] = []
        for child in value:
            items.extend(_string_items(child))
        return items
    if isinstance(value, dict):
        items = []
        for child in value.values():
            items.extend(_string_items(child))
        return items
    return [str(value)]


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value).strip()
    return [text] if text else []
