import logging
from typing import List, Union

from mistralai_azure import ChatCompletionResponse
import openai

from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionTool,
    FunctionMessage,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig


class LLMAgentHelper:

    @staticmethod
    def prep_prompts(
        config: LLMAgentConfig,
        prompt: ChatCompletionRequest,
    ) -> ChatCompletionRequest:
        """
        Prepare the prompt for the LLM by merging pre-defined messages and tools.
        """
        messages = config.get_prefix_messages()
        all_messages = messages + prompt.messages

        tools: List[ChatCompletionTool] = []

        tools_manager = config.get_tools_manager()
        if tools_manager:
            tools.extend(tools_manager.tools)

        if prompt.tools:
            tools.extend(prompt.tools)

        config_dict = config.get_llm_params()
        prompt_dict = prompt.model_dump(exclude_none=True)

        final_prompt = {
            **config_dict,
            **prompt_dict,
            "messages": all_messages,
            "tools": [tool.model_dump(exclude_none=True) for tool in tools],
        }

        return ChatCompletionRequest.model_validate(final_prompt)

    @staticmethod
    def invoke_llm_completion(
        config: LLMAgentConfig,
        prompt: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionResponse:
        """
        Invoke the LLM completion with the given context.
        The fields from the chat completion request, Agent Config, and the LLM are combined.
        The LLM Configuration is used as the base, overwritten by Agent config and then
        the Chat Completion Request.
        """
        ccrequest = LLMAgentHelper.prep_prompts(config, prompt)
        response = llm.completion(ccrequest)
        return response

    @staticmethod
    def process_api_status_error(
        model_name: str,
        ctx: ProcessContext[ChatCompletionRequest],
        status_code: ResponseCodes,
        error: openai.APIStatusError,
        messages: List[
            Union[
                SystemMessage,
                UserMessage,
                AssistantMessage,
                ToolMessage,
                FunctionMessage,
            ]
        ],
    ):  # pragma: no cover
        """
        Process API status error and return a ChatCompletionError object.
        """
        ctx.send_error(
            ChatCompletionError(
                status_code=status_code,
                message=error.message,
                response=error.response.text if error.response else None,
                model=model_name,
                request_messages=messages,
            )
        )  # pragma: no cover

    @staticmethod
    def invoke_llm_and_handle_response(
        agent_name: str,
        config: LLMAgentConfig,
        prompt: ChatCompletionRequest,
        llm: LLM,
        ctx: ProcessContext[ChatCompletionRequest],
    ) -> None:
        """
        Invoke the LLM and handle the response.
        The fields from the chat completion request, Agent Config, and the LLM are combined.
        The LLM Configuration is used as the base, overwritten by Agent config and then
        the Chat Completion Request.
        """
        try:
            chat_response = LLMAgentHelper.invoke_llm_completion(config, prompt, llm)
            ctx.send(chat_response)
        except openai.APIStatusError as e:  # pragma: no cover
            logging.error(f"Error in LLM completion: {e}")
            # Publish the error message
            LLMAgentHelper.process_api_status_error(
                model_name=config.model,
                ctx=ctx,
                status_code=ResponseCodes(e.status_code),
                error=e,
                messages=prompt.messages,
            )
        except Exception as e:  # pragma: no cover
            logging.error(f"Unexpected error in LLM completion: {e}")
            ctx.send_error(
                ChatCompletionError(
                    status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                    message=str(e),
                    model=agent_name,
                    request_messages=prompt.messages,
                )
            )
