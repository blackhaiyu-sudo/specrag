"""Compatibility import for the knowledge-base agent factory."""

from .qa_agents.factory import QAAgentFactory

AgentFactory = QAAgentFactory

__all__ = ["AgentFactory", "QAAgentFactory"]
