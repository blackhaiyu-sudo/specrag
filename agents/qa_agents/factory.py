"""Factory for knowledge-base agents."""

from __future__ import annotations

import logging

from services.generation.llm_response_cleaner import strip_model_reasoning

from .templates.image_analyst import create_image_analyst, TEMPLATES as IA_TEMPLATES
from .templates.image_integration_analyst import (
    create_image_integration_analyst,
    TEMPLATES as IIA_TEMPLATES,
)

logger = logging.getLogger(__name__)


class QAAgentFactory:
    """Create the LLM agents used by the SpecRAG import flow."""

    def __init__(self, config_list=None, logging_service=None):
        self.config_list = config_list
        self.logging_service = logging_service

    def _add_logging_interceptors(self, agent):
        if not self.logging_service or not agent:
            return agent

        try:
            original_generate_reply = agent.generate_reply

            def generate_reply_with_logging(messages, sender=None, **kwargs):
                try:
                    if messages:
                        last_message = messages[-1]
                        if isinstance(last_message, dict) and "content" in last_message:
                            self.logging_service.log_ai_chat_detail(
                                last_message.get("role", "user"),
                                agent.name,
                                last_message.get("content", ""),
                                "接收消息",
                            )
                except Exception as exc:
                    logger.debug("记录 Agent 输入失败: %s", exc)

                if sender is None:
                    reply = original_generate_reply(messages, **kwargs)
                else:
                    reply = original_generate_reply(messages, sender, **kwargs)
                reply = strip_model_reasoning(reply)

                try:
                    if reply:
                        sender_name = sender.name if sender and hasattr(sender, "name") else "系统"
                        self.logging_service.log_ai_message(
                            agent.name,
                            reply,
                            "生成回复",
                            sender_name,
                        )
                except Exception as exc:
                    logger.debug("记录 Agent 输出失败: %s", exc)

                return reply

            agent.generate_reply = generate_reply_with_logging
        except Exception as exc:
            logger.warning("添加 Agent 日志拦截器失败: %s", exc)

        return agent

    def create_image_analyst(self, template_name="默认模式"):
        agent = create_image_analyst(self.config_list, template_name)
        return self._add_logging_interceptors(agent)

    def create_image_integration_analyst(self, template_name="默认模式"):
        agent = create_image_integration_analyst(self.config_list, template_name)
        return self._add_logging_interceptors(agent)

    def get_available_templates(self):
        return {
            "image_analyst": list(IA_TEMPLATES.keys()),
            "image_integration_analyst": list(IIA_TEMPLATES.keys()),
        }
