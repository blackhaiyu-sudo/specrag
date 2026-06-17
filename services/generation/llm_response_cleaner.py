"""
Shared cleanup for model responses.

Some models return private reasoning wrappers such as <think>...</think> even
when prompts ask for plain JSON or Markdown. Downstream agents should never see
that content as requirement facts, and debug artifacts should show the usable
response only.
"""

import re
from typing import Any


REASONING_BLOCK_RE = re.compile(
    r"<(?P<tag>think|analysis)\b[^>]*>.*?</(?P=tag)>",
    flags=re.DOTALL | re.IGNORECASE,
)

REASONING_TAG_RE = re.compile(
    r"</?(?:think|analysis)\b[^>]*>",
    flags=re.IGNORECASE,
)


def strip_model_reasoning(content: Any) -> Any:
    """Remove model reasoning blocks from string content."""
    if not isinstance(content, str):
        return content

    text = content
    previous = None
    while previous != text:
        previous = text
        text = REASONING_BLOCK_RE.sub("", text)

    # If a model emits stray tags without a full pair, remove the tags but keep
    # surrounding content rather than guessing which text is safe to discard.
    text = REASONING_TAG_RE.sub("", text)
    return text.strip()


def has_model_reasoning(content: Any) -> bool:
    """Return whether content contains known reasoning wrapper tags."""
    return isinstance(content, str) and bool(REASONING_TAG_RE.search(content))
