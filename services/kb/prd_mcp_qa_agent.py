"""LLM agent loop that lets the model call SpecRAG MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agents.qa_agents.model_selector import get_models_by_type
from agents.qa_agents.templates.prd_evidence_judge import TEMPLATES as EVIDENCE_TEMPLATES
from config import Config
from services.generation.llm_json_parser import parse_llm_json
from services.generation.llm_response_cleaner import strip_model_reasoning
from services.kb.mcp_server import create_mcp_server


QA_TOOL_ALLOWLIST = {
    "search_units",
    "expand_search",
    "get_unit",
    "get_document",
    "get_units",
    "judge_answerability",
    "synthesize_answer",
    "ask",
}


@dataclass
class MCPQAModelConfig:
    model: str
    api_key: str
    base_url: str


class PRDKBMCPQAAgent:
    """OpenAI-compatible tool-calling agent over the SpecRAG MCP server."""

    def __init__(
        self,
        config_list: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[MCPQAModelConfig] = None,
        timeout: int = 180,
        max_tool_rounds: int = 6,
        max_tool_result_chars: int = 12000,
    ):
        self.config_list = config_list
        self.model_config = model_config
        self.timeout = timeout
        self.max_tool_rounds = max(1, max_tool_rounds)
        self.max_tool_result_chars = max(2000, max_tool_result_chars)
        self.system_message = EVIDENCE_TEMPLATES["MCP知识库问答编排"]["system_message"]
        self._mcp_server = None
        self._tool_schemas: Optional[List[Dict[str, Any]]] = None
        self._resolved_model_config: Optional[MCPQAModelConfig] = None

    def answer(
        self,
        question: str,
        *,
        product: Optional[str] = None,
        version: Optional[str] = None,
        top_k_hint: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = str(question or "").strip()
        if not query:
            raise ValueError("question is required")
        return asyncio.run(self._answer_async(query, product=product, version=version, top_k_hint=top_k_hint))

    async def _answer_async(
        self,
        question: str,
        *,
        product: Optional[str],
        version: Optional[str],
        top_k_hint: Optional[int],
    ) -> Dict[str, Any]:
        started_at = time.time()
        tools = await self._tools()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": build_mcp_qa_user_prompt(question, product=product, version=version, top_k_hint=top_k_hint)},
        ]
        tool_trace: List[Dict[str, Any]] = []
        model_call_trace: List[Dict[str, Any]] = []
        model_meta: Dict[str, Any] = {}

        for _ in range(self.max_tool_rounds):
            message, model_meta = self._call_model(messages, tools=tools)
            model_call_trace.append(compact_model_call_meta(model_meta))
            messages.append(message)
            tool_calls = normalize_tool_calls(message)
            if not tool_calls:
                if not tool_trace:
                    messages.append({
                        "role": "user",
                        "content": (
                            "你还没有调用任何 MCP tool。必须先调用 search_units 或其他 MCP 检索工具，"
                            "不能直接回答。请继续。"
                        ),
                    })
                    continue
                result = normalize_final_answer(message.get("content") or "", question, tool_trace)
                result["model"] = model_meta.get("model")
                result["usage"] = model_meta.get("usage")
                result["duration_seconds"] = round(time.time() - started_at, 3)
                return attach_usage_stats(result, started_at, tool_trace, model_call_trace)

            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                arguments = tool_call["arguments"]
                tool_started = time.time()
                try:
                    tool_payload = await self._call_mcp_tool(tool_name, arguments)
                    tool_error = None
                except Exception as exc:
                    tool_payload = {"error": str(exc)}
                    tool_error = str(exc)
                elapsed = round(time.time() - tool_started, 3)
                summary = summarize_tool_payload(tool_name, tool_payload)
                tool_record = {
                    "tool": tool_name,
                    "arguments": arguments,
                    "duration_seconds": elapsed,
                    "error": tool_error,
                    "result_summary": summary,
                }
                tool_model_meta = extract_tool_model_meta(tool_payload)
                if tool_model_meta:
                    tool_record["model"] = tool_model_meta.get("model")
                    tool_record["usage"] = tool_model_meta.get("usage")
                    tool_record["model_duration_seconds"] = tool_model_meta.get("duration_seconds")
                tool_trace.append(tool_record)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": truncate_json(tool_payload, self.max_tool_result_chars),
                })

                synthesis_result = final_answer_from_synthesis_tool(
                    question=question,
                    tool_name=tool_name,
                    tool_payload=tool_payload,
                    tool_trace=tool_trace,
                    started_at=started_at,
                    model_meta=model_meta,
                )
                if synthesis_result:
                    return attach_usage_stats(synthesis_result, started_at, tool_trace, model_call_trace)

        final_prompt = {
            "role": "user",
            "content": (
                "工具调用轮次已达到上限。请只能基于已经返回的 MCP 工具结果输出最终 JSON；"
                "如果证据不足，answerable=false，并说明缺少什么直接证据。"
            ),
        }
        messages.append(final_prompt)
        message, model_meta = self._call_model(messages, tools=None)
        model_call_trace.append(compact_model_call_meta(model_meta))
        result = normalize_final_answer(message.get("content") or "", question, tool_trace)
        result["model"] = model_meta.get("model")
        result["usage"] = model_meta.get("usage")
        result["duration_seconds"] = round(time.time() - started_at, 3)
        return attach_usage_stats(result, started_at, tool_trace, model_call_trace)

    async def _tools(self) -> List[Dict[str, Any]]:
        if self._tool_schemas is not None:
            return self._tool_schemas

        server = self._server()
        mcp_tools = await server.list_tools()
        schemas = []
        for tool in mcp_tools:
            if tool.name not in QA_TOOL_ALLOWLIST:
                continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or tool.name,
                    "parameters": normalize_json_schema(tool.inputSchema or {"type": "object", "properties": {}}),
                },
            })
        self._tool_schemas = schemas
        return schemas

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in QA_TOOL_ALLOWLIST:
            raise ValueError(f"Tool is not allowed for QA: {tool_name}")
        content, structured = await self._server().call_tool(tool_name, arguments or {})
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        if isinstance(structured, dict):
            return structured
        text_items = []
        for item in content or []:
            text = getattr(item, "text", None)
            if text:
                text_items.append(text)
        if len(text_items) == 1:
            try:
                return json.loads(text_items[0])
            except json.JSONDecodeError:
                return {"text": text_items[0]}
        return {"content": text_items}

    def _server(self):
        if self._mcp_server is None:
            self._mcp_server = create_mcp_server()
        return self._mcp_server

    def _call_model(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        config = self._resolve_model_config()
        payload: Dict[str, Any] = {
            "model": config.model,
            "temperature": 0,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        started_at = time.time()
        response = requests.post(
            f"{config.base_url.rstrip('/')}/chat/completions",
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
            raise RuntimeError("MCP QA model response has no choices")
        raw_message = choices[0].get("message") or {}
        message = normalize_assistant_message(raw_message)
        return message, {
            "model": data.get("model") or config.model,
            "usage": data.get("usage"),
            "duration_seconds": round(time.time() - started_at, 3),
        }

    def _resolve_model_config(self) -> MCPQAModelConfig:
        if self.model_config:
            return self.model_config
        if self._resolved_model_config:
            return self._resolved_model_config

        config_list = self.config_list
        if config_list is None:
            config_list = Config().load_config() or []
        text_configs = get_models_by_type(config_list, model_type="text")
        if not text_configs:
            raise RuntimeError("No text model config found for MCP QA agent")

        cfg = text_configs[0]
        model = str(cfg.get("model") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "").strip()
        if not model or not api_key or not base_url:
            raise RuntimeError("MCP QA model config requires model, api_key and base_url")
        self._resolved_model_config = MCPQAModelConfig(model=model, api_key=api_key, base_url=base_url)
        return self._resolved_model_config


def build_mcp_qa_user_prompt(
    question: str,
    *,
    product: Optional[str],
    version: Optional[str],
    top_k_hint: Optional[int],
) -> str:
    hints = {
        "question": question,
        "product_filter": product or "",
        "version_filter": version or "",
        "top_k_hint": top_k_hint,
    }
    return f"""请使用 SpecRAG MCP tools 回答下面的问题。

【问题与过滤条件】
{json.dumps(hints, ensure_ascii=False, indent=2)}

【要求】
1. 必须先调用 MCP 检索工具，不要直接回答。
2. 你可以自行决定 top_k、是否 expand_search、是否 get_unit。
3. 如果证据不足，最终 answerable=false。
4. 最终只输出 JSON。
"""


def normalize_assistant_message(raw_message: Dict[str, Any]) -> Dict[str, Any]:
    message = {
        "role": "assistant",
        "content": strip_model_reasoning(raw_message.get("content") or "").strip(),
    }
    if raw_message.get("tool_calls"):
        message["tool_calls"] = raw_message.get("tool_calls")
    if raw_message.get("function_call"):
        message["function_call"] = raw_message.get("function_call")
    return message


def normalize_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, tool_call in enumerate(message.get("tool_calls") or []):
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        normalized.append({
            "id": str(tool_call.get("id") or f"tool_call_{index}"),
            "name": name,
            "arguments": parse_tool_arguments(function.get("arguments")),
        })
    function_call = message.get("function_call")
    if function_call:
        name = str(function_call.get("name") or "").strip()
        if name:
            normalized.append({
                "id": "function_call",
                "name": name,
                "arguments": parse_tool_arguments(function_call.get("arguments")),
            })
    return normalized


def parse_tool_arguments(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(schema or {})
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    return normalized


def normalize_final_answer(content: str, question: str, tool_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = strip_model_reasoning(content or "").strip()
    parsed = parse_final_answer_payload(text)
    if not isinstance(parsed, dict):
        parsed = {
            "answerable": False,
            "answer": "当前知识库未找到明确说明，不能根据相近内容推断。",
            "reason": "model did not return a JSON object",
            "sources": [],
        }

    answerable = bool(parsed.get("answerable"))
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        answer = "当前知识库未找到明确说明，不能根据相近内容推断。"
        answerable = False
    sources = parsed.get("sources") if isinstance(parsed.get("sources"), list) else []
    return {
        "question": question,
        "answerable": answerable,
        "answer": answer,
        "reason": str(parsed.get("reason") or "").strip(),
        "sources": sources,
        "tool_trace": tool_trace,
        "backend_tool_trace": tool_trace,
        "raw_final": text,
    }


def attach_usage_stats(
    result: Dict[str, Any],
    started_at: float,
    tool_trace: List[Dict[str, Any]],
    model_call_trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    duration_seconds = round(time.time() - started_at, 3)
    result["duration_seconds"] = duration_seconds
    result["usage_stats"] = build_usage_stats(
        duration_seconds=duration_seconds,
        tool_trace=tool_trace,
        model_call_trace=model_call_trace,
    )
    result["model_call_trace"] = model_call_trace
    return result


def build_usage_stats(
    *,
    duration_seconds: float,
    tool_trace: List[Dict[str, Any]],
    model_call_trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    direct_usage = [item.get("usage") for item in model_call_trace if isinstance(item.get("usage"), dict)]
    tool_usage = [item.get("usage") for item in tool_trace if isinstance(item.get("usage"), dict)]
    all_usage = direct_usage + tool_usage
    tool_duration = round(sum(float(item.get("duration_seconds") or 0) for item in tool_trace), 3)
    llm_duration = round(
        sum(float(item.get("duration_seconds") or 0) for item in model_call_trace)
        + sum(float(item.get("model_duration_seconds") or 0) for item in tool_trace),
        3,
    )
    return {
        "duration_seconds": duration_seconds,
        "tool_call_count": len(tool_trace),
        "model_call_count": len(model_call_trace) + len(tool_usage),
        "tool_duration_seconds": tool_duration,
        "llm_duration_seconds": llm_duration,
        "token_usage": sum_token_usage(all_usage),
        "direct_model_token_usage": sum_token_usage(direct_usage),
        "tool_model_token_usage": sum_token_usage(tool_usage),
    }


def sum_token_usage(usages: List[Dict[str, Any]]) -> Dict[str, int]:
    total = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
    }
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        total["prompt_tokens"] += safe_int(usage.get("prompt_tokens"))
        total["completion_tokens"] += safe_int(usage.get("completion_tokens"))
        total["total_tokens"] += safe_int(usage.get("total_tokens"))
        completion_details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        if isinstance(completion_details, dict):
            total["reasoning_tokens"] += safe_int(completion_details.get("reasoning_tokens"))
        if isinstance(prompt_details, dict):
            total["cached_tokens"] += safe_int(prompt_details.get("cached_tokens"))
    return total


def compact_model_call_meta(model_meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model": model_meta.get("model"),
        "usage": model_meta.get("usage"),
        "duration_seconds": model_meta.get("duration_seconds"),
    }


def extract_tool_model_meta(tool_payload: Any) -> Dict[str, Any]:
    if not isinstance(tool_payload, dict):
        return {}
    for key in ("answerability", "answer_synthesis"):
        value = tool_payload.get(key)
        if isinstance(value, dict) and (value.get("usage") or value.get("model") or value.get("duration_seconds")):
            return {
                "model": value.get("model"),
                "usage": value.get("usage"),
                "duration_seconds": value.get("duration_seconds"),
            }
    return {}


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def final_answer_from_synthesis_tool(
    *,
    question: str,
    tool_name: str,
    tool_payload: Dict[str, Any],
    tool_trace: List[Dict[str, Any]],
    started_at: float,
    model_meta: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if tool_name != "synthesize_answer" or not isinstance(tool_payload, dict):
        return None

    synthesis = tool_payload.get("answer_synthesis") or {}
    if not isinstance(synthesis, dict):
        return None
    answer = str(synthesis.get("synthesized_answer") or "").strip()
    if not answer:
        return None

    sources = tool_payload.get("sources") if isinstance(tool_payload.get("sources"), list) else []
    return {
        "question": question,
        "answerable": True,
        "answer": answer,
        "reason": "基于 synthesize_answer 工具结果生成",
        "sources": sources,
        "tool_trace": tool_trace,
        "backend_tool_trace": tool_trace,
        "raw_final": json.dumps({
            "answerable": True,
            "answer": answer,
            "reason": "基于 synthesize_answer 工具结果生成",
            "sources": sources,
        }, ensure_ascii=False),
        "model": model_meta.get("model"),
        "usage": model_meta.get("usage"),
        "duration_seconds": round(time.time() - started_at, 3),
    }


def parse_final_answer_payload(text: str) -> Dict[str, Any]:
    """Parse the final QA JSON, tolerating unescaped quotes in answer text."""
    try:
        parsed = parse_llm_json(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    repaired = parse_jsonish_final_answer(text)
    if repaired:
        return repaired

    return {
        "answerable": False,
        "answer": text or "当前知识库未找到明确说明，不能根据相近内容推断。",
        "reason": "model did not return valid JSON",
        "sources": [],
    }


def parse_jsonish_final_answer(text: str) -> Dict[str, Any]:
    """Extract stable final-answer fields from JSON-like text with invalid string escaping."""
    payload = _extract_jsonish_object(text)
    if not payload:
        return {}

    answerable = _extract_jsonish_bool(payload, "answerable")
    answer = _extract_jsonish_string_between(payload, "answer", "reason")
    reason = _extract_jsonish_string_between(payload, "reason", "sources")
    sources = _extract_jsonish_sources(payload)
    if answerable is None and not answer and not reason and not sources:
        return {}
    return {
        "answerable": bool(answerable),
        "answer": answer,
        "reason": reason or "model final JSON repaired from invalid string escaping",
        "sources": sources,
    }


def _extract_jsonish_object(text: str) -> str:
    raw = str(text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return raw[start:end + 1]


def _extract_jsonish_bool(text: str, key: str) -> Optional[bool]:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _extract_jsonish_string_between(text: str, key: str, next_key: str) -> str:
    pattern = rf'"{re.escape(key)}"\s*:\s*"(.*?)"\s*,\s*"{re.escape(next_key)}"\s*:'
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    return _clean_jsonish_string(match.group(1))


def _extract_jsonish_sources(text: str) -> List[Dict[str, Any]]:
    match = re.search(r'"sources"\s*:\s*(\[.*?\])\s*[,}]', text, flags=re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _clean_jsonish_string(value: str) -> str:
    return (
        str(value or "")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .strip()
    )


def summarize_tool_payload(tool_name: str, payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return str(type(payload).__name__)
    if payload.get("error"):
        return f"error: {payload.get('error')}"
    if tool_name in {"search_units", "expand_search"}:
        results = payload.get("results") or []
        units = [f"{item.get('unit_id')} {((item.get('unit') or {}).get('title') or item.get('unit_title') or '')}" for item in results[:5]]
        return f"{len(results)} results: " + "; ".join(units)
    if tool_name == "judge_answerability":
        answerability = payload.get("answerability") or payload
        return f"should_answer={answerability.get('should_answer')}"
    if tool_name == "synthesize_answer":
        synthesis = payload.get("answer_synthesis") or payload
        return str(synthesis.get("synthesized_answer") or "")[:160]
    if tool_name == "get_unit":
        unit = payload.get("unit") or payload
        return f"{unit.get('unit_id')} {unit.get('title')}"
    return truncate_json(payload, 400)


def truncate_json(value: Any, max_chars: int) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[TRUNCATED]"
