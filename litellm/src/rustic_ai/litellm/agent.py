from collections import deque
from datetime import datetime
import logging
from typing import Deque, List, Optional, Union

from dotenv import load_dotenv
import litellm
from litellm import validate_environment
import openai

from rustic_ai.core.guild.agent import (
    Agent,
    ProcessContext,
    processor,
)
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseEmpty,
    ChatCompletionTool,
    FileContentPart,
    FunctionMessage,
    ImageContentPart,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolsManager
from rustic_ai.litellm.utils import ResponseUtils

from .conf import LiteLLMConf

load_dotenv()


class LiteLLMAgent(Agent[LiteLLMConf]):
    """
    LiteLLM agent for invoking various LLM models using LiteLLM.
    """

    litellm.drop_params = True

    def __init__(self):
        validation_result = validate_environment(self.config.model)
        if not validation_result.get("keys_in_environment"):
            missing_keys = validation_result.get("missing_keys", [])
            raise RuntimeError(f"Required environment variable(s) {'{}'.join(missing_keys)} not set")

        self.pre_messages = self.config.messages

        self.model = self.config.model
        self.client_props = self.config.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_none=True,
            exclude={
                "message_memory",
                "toolset",
                "filter_attachments",
                "extract_tool_calls",
                "skip_chat_response_on_tool_call",
                "retries_on_tool_parse_error",
            },
        )
        self.message_memory_size = self.config.message_memory or 0
        self.message_queue: Deque[SystemMessage | UserMessage | AssistantMessage | ToolMessage | FunctionMessage] = (
            deque(maxlen=self.message_memory_size)
        )
        self.filter_attachments = self.config.filter_attachments
        self.tools_manager: Optional[ToolsManager] = self.config.get_tools_manager()

        self.extract_tool_calls = self.config.extract_tool_calls
        self.skip_chat_response_on_tool_call = self.config.skip_chat_response_on_tool_call
        self.retries_on_tool_parse_error = self.config.retries_on_tool_parse_error

    @processor(ChatCompletionRequest)
    def llm_completion(self, ctx: ProcessContext[ChatCompletionRequest]):

        prompt = ctx.payload

        messages = self.pre_messages if self.pre_messages else []

        user_messages = prompt.messages
        send_messages = user_messages

        if user_messages and self.filter_attachments:
            # Filter out attachments from user messages
            filtered_messages = []
            for msg in user_messages:
                if isinstance(msg, UserMessage) and isinstance(msg.content, ArrayOfContentParts):
                    msg.content = [
                        content
                        for content in msg.content
                        if not isinstance(content, FileContentPart) and not isinstance(content, ImageContentPart)
                    ]
                    if msg.content:
                        filtered_messages.append(msg)
                else:
                    filtered_messages.append(msg)

            send_messages = filtered_messages

        if send_messages:
            all_messages = messages + list(self.message_queue) + send_messages

            messages_dict = [m.model_dump(exclude_none=True) for m in all_messages]

            tools: List[ChatCompletionTool] = self.tools_manager.tools if self.tools_manager else []
            if prompt.tools:
                tools.extend(prompt.tools)

            full_prompt = {
                **self.client_props,
                **prompt.model_dump(exclude_unset=True, exclude_none=True),
                "messages": messages_dict,
            }

            if tools:
                # Convert ChatCompletionTool objects to dictionaries for litellm
                full_prompt["tools"] = [tool.model_dump(exclude_none=True) for tool in tools]

            response = self._invoke_llm_and_process_response(ctx, full_prompt, all_messages)

            if response:

                # Update the message queue with the new messages
                self.message_queue.extend(
                    prompt.messages
                )  # Append the prompt messages (from user) to the message queue
                if response.choices and response.choices[0].message:
                    self.message_queue.append(
                        response.choices[0].message
                    )  # Append the response message (from LLM) to the message queue
        else:
            # No messages to send, return an error
            ctx.send(
                ChatCompletionResponseEmpty(
                    id=f"chatcmpl-{prompt.id}",
                    created=int(datetime.now().timestamp()),
                )
            )

    def _invoke_llm_and_process_response(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        full_prompt: dict,
        all_messages: List[Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage, FunctionMessage]],
        call_count: int = 0,
    ) -> Optional[ChatCompletionResponse]:
        """
        Invoke the LLM and process the response.
        """
        try:
            completion = litellm.completion(**full_prompt)

            response: ChatCompletionResponse = ResponseUtils.from_litellm(completion)

            if response:
                if self.tools_manager and self.extract_tool_calls:
                    # Extract tool calls from the response
                    try:
                        tool_calls = self.tools_manager.extract_tool_calls(response)
                        if tool_calls:
                            # If tool calls are found, publish them
                            for tool_call in tool_calls:
                                ctx.send(tool_call)

                            # If skip_chat_response_on_tool_call is set, skip publishing the chat response
                            if self.skip_chat_response_on_tool_call:
                                return response  # We still return the response for tracking purposes
                    except Exception as e:
                        ctx.send_error(
                            ChatCompletionError(
                                status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                                message=f"Error extracting tool calls: {e}",
                                response=None,
                                model=self.model,
                                request_messages=all_messages,
                            )
                        )
                        # Retry the LLM completion if tool parse error occurs
                        # This is a workaround for the LLM returning invalid tool calls
                        if call_count <= self.retries_on_tool_parse_error:
                            call_count += 1
                            self._invoke_llm_and_process_response(
                                ctx=ctx,
                                full_prompt=full_prompt,
                                all_messages=all_messages,
                                call_count=call_count,
                            )
                        else:
                            ctx.send_error(
                                ChatCompletionError(
                                    status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                                    message="Max retries reached for tool parse error",
                                    response=None,
                                    model=self.model,
                                    request_messages=all_messages,
                                )
                            )
                            return None
                ctx.send(response)
            return response
        except openai.APIStatusError as e:  # pragma: no cover
            logging.error(f"Error in LLM completion: {e}")
            # Publish the error message
            self.process_api_status_error(
                ctx=ctx,
                status_code=ResponseCodes(e.status_code),
                error=e,
                messages=all_messages,
            )
            return None

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
