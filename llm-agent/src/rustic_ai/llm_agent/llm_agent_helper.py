import logging
from typing import List, Union

import openai

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    FunctionMessage,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig


class LLMAgentHelper:

    @staticmethod
    def invoke_llm_completion(
        agent: Agent,
        config: LLMAgentConfig,
        llm: LLM,
        ctx: ProcessContext[ChatCompletionRequest],
        prompt: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """
        Invoke the LLM completion with the given context.
        The fields from the chat completion request, Agent Config, and the LLM are combined.
        The LLM Configuration is used as the base, overwritten by Agent config and then
        the Chat Completion Request.
        """

        pre_processors = config.request_preprocessors or []
        wrap_processors = config.llm_request_wrappers or []
        post_processors = config.response_postprocessors or []

        for pre_processor in pre_processors:
            prompt = pre_processor.preprocess(agent=agent, ctx=ctx, request=prompt)

        for wrap_processor in wrap_processors:
            prompt = wrap_processor.preprocess(agent=agent, ctx=ctx, request=prompt)

        config_dict = config.get_llm_params()
        prompt_dict = prompt.model_dump(exclude_none=True)

        final_prompt = {
            **config_dict,
            **prompt_dict,
        }

        ccrequest: ChatCompletionRequest = ChatCompletionRequest.model_validate(final_prompt)

        response = llm.completion(ccrequest)

        for wrap_processor in reversed(wrap_processors):
            wrap_processor.postprocess(agent=agent, ctx=ctx, final_prompt=ccrequest, llm_response=response)

        for post_processor in post_processors:
            post_processor.postprocess(agent=agent, ctx=ctx, final_prompt=ccrequest, llm_response=response)

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
    ) -> ChatCompletionError:  # pragma: no cover
        """
        Process API status error and return a ChatCompletionError object.
        """
        error = ChatCompletionError(
            status_code=status_code,
            message=error.message,
            response=error.response.text if error.response else None,
            model=model_name,
            request_messages=messages,
        )

        ctx.send_error(error)  # pragma: no cover
        return error

    @staticmethod
    def invoke_llm_and_handle_response(
        agent: Agent,
        config: LLMAgentConfig,
        llm: LLM,
        ctx: ProcessContext[ChatCompletionRequest],
        prompt: ChatCompletionRequest,
    ) -> ChatCompletionResponse | ChatCompletionError:
        """
        Invoke the LLM and handle the response.
        The fields from the chat completion request, Agent Config, and the LLM are combined.
        The LLM Configuration is used as the base, overwritten by Agent config and then
        the Chat Completion Request.
        """
        try:
            chat_response = LLMAgentHelper.invoke_llm_completion(agent, config, llm, ctx, prompt)
            ctx.send(chat_response)
            return chat_response
        except openai.APIStatusError as e:  # pragma: no cover
            logging.error(f"Error in LLM completion: {e}")
            # Publish the error message
            return LLMAgentHelper.process_api_status_error(
                model_name=config.model,
                ctx=ctx,
                status_code=ResponseCodes(e.status_code),
                error=e,
                messages=ctx.payload.messages,
            )
        except Exception as e:  # pragma: no cover
            logging.error(f"Unexpected error in LLM completion: {e}")
            error = ChatCompletionError(
                status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                message=str(e),
                model=agent.name,
                request_messages=ctx.payload.messages,
            )

            ctx.send_error(error)
            return error
