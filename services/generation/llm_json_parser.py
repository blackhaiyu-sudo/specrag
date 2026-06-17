"""
LLM JSON parsing helpers.

The pipeline asks agents for JSON, but model responses may still include
Markdown fences or short explanations. Keep extraction centralized so the
generation flow does not depend on ad hoc string slicing.
"""

import json
import logging
import re
from typing import Any

from services.generation.llm_response_cleaner import strip_model_reasoning

logger = logging.getLogger(__name__)


class LLMJsonParseError(ValueError):
    """Raised when a model response cannot be parsed as JSON."""


def parse_llm_json(content: str) -> Any:
    """Parse a JSON object/array from an LLM response."""
    if not content or not str(content).strip():
        raise LLMJsonParseError("empty response")

    text = strip_model_reasoning(str(content)).strip()

    # Fast path: exact JSON.
    try:
        return _loads_json(text)
    except json.JSONDecodeError:
        pass

    # Common path: fenced code block.
    for block in _iter_fenced_blocks(text):
        try:
            return _loads_json(block)
        except json.JSONDecodeError:
            continue

    # Fallback: bracket-balanced JSON object/array embedded in text.
    candidate = _extract_balanced_json(text)
    if candidate:
        try:
            return _loads_json(candidate)
        except json.JSONDecodeError as exc:
            raise LLMJsonParseError(f"invalid embedded JSON: {exc}") from exc

    raise LLMJsonParseError("no JSON object or array found")


def _loads_json(text: str) -> Any:
    """Load JSON, allowing narrow repairs for common LLM JSON drift."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_missing_key_opening_quotes(text)
        repaired = _repair_missing_object_start_in_arrays(repaired)
        repaired = _repair_stray_object_close_before_array_close(repaired)
        if repaired != text:
            return json.loads(repaired)
        raise


def _iter_fenced_blocks(text: str):
    pattern = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        if block:
            yield block


def _repair_missing_key_opening_quotes(text: str) -> str:
    """
    Repair only object-key quote omissions such as {id":"REQ001"} or {id:...}.

    Some models occasionally drop the opening quote for an object key while still
    otherwise emitting JSON. This keeps the parser strict for values and overall
    structure instead of accepting arbitrary JavaScript-like objects.
    """
    result = []
    i = 0
    in_string = False
    escape = False

    while i < len(text):
        char = text[i]

        if escape:
            result.append(char)
            escape = False
            i += 1
            continue

        if in_string and char == "\\":
            result.append(char)
            escape = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = not in_string
            i += 1
            continue

        if not in_string and char in "{,":
            result.append(char)
            i += 1
            while i < len(text) and text[i].isspace():
                result.append(text[i])
                i += 1

            if i < len(text) and (text[i].isalpha() or text[i] == "_"):
                key_start = i
                key_end = i + 1
                while key_end < len(text) and (text[key_end].isalnum() or text[key_end] == "_"):
                    key_end += 1

                # Missing opening quote only: {id":"REQ001"}
                if key_end < len(text) and text[key_end] == '"':
                    colon_pos = key_end + 1
                    while colon_pos < len(text) and text[colon_pos].isspace():
                        colon_pos += 1
                    if colon_pos < len(text) and text[colon_pos] == ":":
                        result.append('"')
                        result.append(text[key_start:key_end])
                        result.append('"')
                        i = key_end + 1
                        continue

                # Unquoted key: {id:"REQ001"}
                colon_pos = key_end
                while colon_pos < len(text) and text[colon_pos].isspace():
                    colon_pos += 1
                if colon_pos < len(text) and text[colon_pos] == ":":
                    result.append('"')
                    result.append(text[key_start:key_end])
                    result.append('"')
                    i = key_end
                    continue

            continue

        result.append(char)
        i += 1

    return "".join(result)


def _repair_missing_object_start_in_arrays(text: str) -> str:
    """
    Repair array items that lost the opening object brace: ...},{"id":"LU002"...}

    This is intentionally limited to the pipeline's stable id-shaped objects and
    only fires after an object close followed by a new id key.
    """
    return re.sub(
        r'(\})(\s*,\s*)("id"\s*:\s*"(?:REQ|LU|M|TP)\d{3,4}")',
        r'\1\2{\3',
        text,
    )


def _repair_stray_object_close_before_array_close(text: str) -> str:
    """
    Repair a narrow LLM JSON drift: ["a", "b"}] should be ["a", "b"].

    This only removes a non-string `}` when the parser is currently inside an
    array and the next non-space token is `]`. It does not change quoted text or
    rebalance arbitrary malformed JSON.
    """
    result = []
    stack = []
    i = 0
    in_string = False
    escape = False

    while i < len(text):
        char = text[i]

        if escape:
            result.append(char)
            escape = False
            i += 1
            continue

        if in_string and char == "\\":
            result.append(char)
            escape = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = not in_string
            i += 1
            continue

        if in_string:
            result.append(char)
            i += 1
            continue

        if char in "{[":
            stack.append(char)
            result.append(char)
            i += 1
            continue

        if char == "}" and stack and stack[-1] == "[":
            next_pos = i + 1
            while next_pos < len(text) and text[next_pos].isspace():
                next_pos += 1
            if next_pos < len(text) and text[next_pos] == "]":
                i += 1
                continue

        if char == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            result.append(char)
            i += 1
            continue

        if char == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            result.append(char)
            i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


def _extract_balanced_json(text: str) -> str:
    start_positions = [pos for pos in (text.find("{"), text.find("[")) if pos != -1]
    if not start_positions:
        return ""

    start = min(start_positions)
    open_char = text[start]
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        char = text[idx]

        if escape:
            escape = False
            continue

        if char == "\\":
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1].strip()

    logger.debug("balanced JSON extraction failed: unmatched brackets")
    return ""
