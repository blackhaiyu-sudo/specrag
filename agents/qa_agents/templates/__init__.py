"""Agent templates used by SpecRAG."""

from .image_analyst import create_image_analyst, TEMPLATES as IA_TEMPLATES
from .image_integration_analyst import create_image_integration_analyst, TEMPLATES as IIA_TEMPLATES
from .prd_evidence_judge import (
    TEMPLATES as PEJ_TEMPLATES,
    build_answer_synthesis_prompt,
    build_evidence_judge_prompt,
    create_prd_evidence_judge,
    create_prd_evidence_synthesizer,
    create_prd_kb_mcp_qa_agent,
)
from .prd_kb_cleaner import create_prd_kb_cleaner, TEMPLATES as PKBC_TEMPLATES
from .prd_query_hint_generator import (
    create_prd_query_hint_generator,
    TEMPLATES as PQHG_TEMPLATES,
)

__all__ = [
    "create_image_analyst",
    "IA_TEMPLATES",
    "create_image_integration_analyst",
    "IIA_TEMPLATES",
    "create_prd_kb_cleaner",
    "PKBC_TEMPLATES",
    "create_prd_query_hint_generator",
    "PQHG_TEMPLATES",
    "create_prd_kb_mcp_qa_agent",
    "create_prd_evidence_judge",
    "create_prd_evidence_synthesizer",
    "build_answer_synthesis_prompt",
    "build_evidence_judge_prompt",
    "PEJ_TEMPLATES",
]
