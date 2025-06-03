import logging
import re

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.messaging.core.message import AgentTag, FunctionalTransformer
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class LLMXformLambdas:

    _tag_pattern = re.compile(r"@([a-zA-Z0-9_-]+)")

    @staticmethod
    def ccres2ccreq(payload: dict) -> dict:
        """Converts a ChatCompletionRequest to a ChatCompletionResponse."""

        try:
            ccresp = ChatCompletionResponse.model_validate(payload)
            return {
                "payload": ChatCompletionRequest(messages=[ccresp.choices[0].message]).model_dump(),
                "format": get_qualified_class_name(ChatCompletionRequest),
            }

        except Exception as e:
            logging.error(f"Failed to validate payload: {e}")
            return {}

    @staticmethod
    def extract_agent_tags(payload: dict) -> dict:
        """Extracts agent tags from a ChatCompletionRequest."""

        try:
            ccresp = ChatCompletionResponse.model_validate(payload)
            message = ccresp.choices[0].message.content
            agent_ats = re.findall(LLMXformLambdas._tag_pattern, message)

            agent_tags = [AgentTag(id=tag) for tag in agent_ats]
            return {
                "recipient_list": agent_tags,
            }
        except Exception as e:
            logging.error(f"Failed to validate payload: {e}")
            return {}

    @classmethod
    def register_helpers(cls):
        """Registers the helper functions as lambdas."""
        FunctionalTransformer.register_lambda(
            name="ccres2ccreq",
            func=cls.ccres2ccreq,
        )
        FunctionalTransformer.register_lambda(
            name="extract_agent_tags",
            func=cls.extract_agent_tags,
        )
