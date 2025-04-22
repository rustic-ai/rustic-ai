import logging
from collections import deque
from typing import Deque, List, Union

import openai
from dotenv import load_dotenv

import litellm
from litellm import validate_environment
from rustic_ai.core.guild.agent import (
    Agent,
    AgentMode,
    AgentType,
    ProcessContext,
    processor,
)
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionTool,
    FunctionMessage,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.litellm.utils import ResponseUtils

from .conf import LiteLLMConf

load_dotenv()


class LiteLLMAgent(Agent[LiteLLMConf]):
    """
    LiteLLM agent for invoking various LLM models using LiteLLM.
    """

    litellm.drop_params = True

    def __init__(self, agent_spec: AgentSpec[LiteLLMConf]):
        validation_result = validate_environment(agent_spec.props.model)
        if not validation_result.get("keys_in_environment"):
            missing_keys = validation_result.get("missing_keys", [])
            raise RuntimeError(f"Required environment variable(s) {'{}'.join(missing_keys)} not set")

        super().__init__(agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.pre_messages = agent_spec.props.messages
        self.pre_tools = agent_spec.props.tools
        self.model = agent_spec.props.model
        self.client_props = agent_spec.props.model_dump(
            mode="json", exclude_unset=True, exclude_none=True, exclude={"message_memory"}
        )
        self.message_memory_size = agent_spec.props.message_memory or 0
        self.message_queue: Deque[SystemMessage | UserMessage | AssistantMessage | ToolMessage | FunctionMessage] = (
            deque(maxlen=self.message_memory_size)
        )

    @processor(ChatCompletionRequest)
    def llm_completion(self, ctx: ProcessContext[ChatCompletionRequest]):

        prompt = ctx.payload

        messages = self.pre_messages if self.pre_messages else []

        all_messages = messages + list(self.message_queue) + prompt.messages

        messages_dict = [m.model_dump(exclude_none=True) for m in all_messages]

        tools: List[ChatCompletionTool] = self.pre_tools if self.pre_tools else []
        if prompt.tools:
            tools.extend(prompt.tools)

        full_prompt = {
            **self.client_props,
            **prompt.model_dump(exclude_unset=True, exclude_none=True),
            "messages": messages_dict,
        }

        if tools:
            full_prompt["tools"] = tools

        try:
            completion = litellm.completion(**full_prompt)

            response: ChatCompletionResponse = ResponseUtils.from_litellm(completion)

            self.message_queue.extend(prompt.messages)  # Append the prompt messages (from user) to the message queue
            if response.choices and response.choices[0].message:
                self.message_queue.append(
                    response.choices[0].message
                )  # Append the response message (from LLM) to the message queue

            if response:
                ctx.send(response)

        except openai.APIStatusError as e:  # pragma: no cover
            logging.error(f"Error in LLM completion: {e}")
            # Publish the error message
            self.process_api_status_error(
                ctx=ctx,
                status_code=ResponseCodes(e.status_code),
                error=e,
                messages=messages,
            )

    def process_api_status_error(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        status_code: ResponseCodes,
        error: openai.APIStatusError,
        messages: List[Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage, FunctionMessage]],
    ):  # pragma: no cover
        """
        Process API status error and return a ChatCompletionError object.
        """
        ctx.send_error(
            ChatCompletionError(
                status_code=status_code,
                message=error.message,
                response=error.response.text if error.response else None,
                model=self.model,
                request_messages=messages,
            )
        )  # pragma: no cover
