"""
Utilities for extracting the actual PRD body from model responses.

Source PRDs are later cleaned into requirement units. Keep this cleanup narrow:
remove model wrappers and integration reports, not business content inside the
PRD.
"""

import re
from typing import Iterable

from services.generation.llm_response_cleaner import strip_model_reasoning


def clean_prd_document(content: str) -> str:
    """Return a PRD-only document from a model response or stored PRD field."""
    text = str(content or "").strip()
    if not text:
        return ""

    text = _extract_marked_prd(text)
    text = strip_model_reasoning(text)
    text = _strip_outer_markdown_fence(text)
    text = _trim_before_prd_heading(text)
    text = _remove_legacy_confirm_blocks(text)
    text = _trim_after_non_prd_report(text)
    text = _repair_markdown_table_separator_rows(text)
    return text.strip()


def _extract_marked_prd(text: str) -> str:
    start_marker = "<PRD_DOCUMENT_START>"
    end_markers = ("</PRD_DOCUMENT_END>", "<PRD_DOCUMENT_END>")

    start_idx = text.find(start_marker)
    if start_idx == -1:
        return text

    content_start = start_idx + len(start_marker)
    end_idx = -1
    for marker in end_markers:
        idx = text.find(marker, content_start)
        if idx != -1:
            end_idx = idx
            break

    if end_idx == -1 or end_idx <= content_start:
        return text
    return text[content_start:end_idx].strip()


def _strip_outer_markdown_fence(text: str) -> str:
    match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)```", text.strip(), flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _trim_before_prd_heading(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("# "):
            continue
        if any(keyword in stripped for keyword in ("PRD", "需求", "产品文档", "产品说明")):
            return "\n".join(lines[index:]).strip()
    return text


def _trim_after_non_prd_report(text: str) -> str:
    lines = text.splitlines()
    cut_index = None
    for index, line in enumerate(lines):
        heading = line.strip().lstrip("#").strip()
        normalized = re.sub(r"\s+", "", heading)
        if _is_non_prd_report_heading(normalized):
            cut_index = _trim_preceding_separator(lines, index)
            break

    if cut_index is None:
        return text
    return "\n".join(lines[:cut_index]).rstrip()


def _remove_legacy_confirm_blocks(text: str) -> str:
    """Remove unresolved non-source blocks from legacy PRD body text."""
    if "<HUMAN_CONFIRM_START>" not in text:
        return text

    cleaned = re.sub(
        r"```[^\n]*\n?\s*<HUMAN_CONFIRM_START>.*?<HUMAN_CONFIRM_END>\s*```",
        "",
        text,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<HUMAN_CONFIRM_START>.*?<HUMAN_CONFIRM_END>",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _repair_markdown_table_separator_rows(text: str) -> str:
    lines = text.splitlines()
    repaired: list[str] = []
    for index, line in enumerate(lines):
        if not _is_table_row(line):
            repaired.append(line)
            continue
        previous_line = lines[index - 1] if index > 0 else ""
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if _is_table_row(previous_line) and _is_table_row(next_line) and _looks_like_broken_separator(line):
            cell_count = max(1, len(line.strip().strip("|").split("|")))
            repaired.append("| " + " | ".join(["---"] * cell_count) + " |")
            continue
        repaired.append(line)
    return "\n".join(repaired)


def _is_table_row(line: str) -> bool:
    stripped = str(line or "").strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _looks_like_broken_separator(line: str) -> bool:
    cells = [cell.strip() for cell in str(line or "").strip().strip("|").split("|")]
    if not cells:
        return False
    separator_cells = [cell for cell in cells if re.fullmatch(r":?-{3,}:?", cell)]
    return len(separator_cells) >= max(1, len(cells) - 1)


def _is_non_prd_report_heading(normalized_heading: str) -> bool:
    exact_headings = {
        "整合清单",
        "已整合的确认问题",
        "待确认问题",
        "整合统计",
        "整合方式分布",
        "关键信息保留",
    }
    if normalized_heading in exact_headings:
        return True
    return normalized_heading.startswith("已整合的确认问题") or normalized_heading.startswith("待确认问题")


def _trim_preceding_separator(lines: Iterable[str], index: int) -> int:
    result = index
    while result > 0 and not str(lines[result - 1]).strip():
        result -= 1
    if result > 0 and re.fullmatch(r"-{3,}", str(lines[result - 1]).strip()):
        result -= 1
    return result
