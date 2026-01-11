import logging
from typing import List, Optional, Union

import openai

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    LLMMessage,
    ResponseCodes,
)
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor


class LLMAgentHelper:

    @staticmethod
    def invoke_llm_completion(
        agent: Agent,
        config: LLMAgentConfig,
        llm: LLM,
        ctx: ProcessContext[ChatCompletionRequest],
        prompt: ChatCompletionRequest,
    ) -> Union[ChatCompletionResponse, ChatCompletionError]:
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
            prompt = pre_processor.preprocess(agent=agent, ctx=ctx, request=prompt, llm=llm)

        for wrap_processor in wrap_processors:
            prompt = wrap_processor.preprocess(agent=agent, ctx=ctx, request=prompt, llm=llm)

        config_dict = config.get_llm_params()
        prompt_dict = prompt.model_dump(exclude_none=True)

        final_prompt = {
            **config_dict,
            **prompt_dict,
        }

        cc_request: ChatCompletionRequest = ChatCompletionRequest.model_validate(final_prompt)

        max_retries = config.max_retries

        return LLMAgentHelper._invoke_llm_completion(
            agent=agent,
            ctx=ctx,
            llm=llm,
            cc_request=cc_request,
            wrap_processors=wrap_processors,
            post_processors=post_processors,
            max_retries=max_retries,
            model=config.model,
        )

    @staticmethod
    def _invoke_llm_completion(
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        cc_request: ChatCompletionRequest,
        wrap_processors: List[LLMCallWrapper],
        post_processors: List[ResponsePostprocessor],
        max_retries: int,
        model: Optional[str] = None,
    ) -> Union[ChatCompletionResponse, ChatCompletionError]:

        response = llm.completion(cc_request, model)

        new_messages = []

        try:
            for wrap_processor in reversed(wrap_processors):
                post_msg = wrap_processor.postprocess(
                    agent=agent,
                    ctx=ctx,
                    final_prompt=cc_request,
                    llm_response=response,
                    llm=llm,
                )
                if post_msg:
                    new_messages.extend(post_msg)

            for post_processor in post_processors:
                post_msg = post_processor.postprocess(
                    agent=agent,
                    ctx=ctx,
                    final_prompt=cc_request,
                    llm_response=response,
                    llm=llm,
                )
                if post_msg:
                    new_messages.extend(post_msg)

            reasoning = response.choices[0].message.reasoning_content if response.choices else ""

            for msg in new_messages:
                if reasoning:
                    ctx.send(msg, reason=reasoning)
                else:
                    ctx.send(msg)

        except Exception as e:  # pragma: no cover
            logging.error(f"Error in post processing: {e}")
            if max_retries > 0:
                logging.info(f"Retrying LLM call, remaining retries: {max_retries}")
                return LLMAgentHelper._invoke_llm_completion(
                    agent=agent,
                    ctx=ctx,
                    llm=llm,
                    cc_request=cc_request,
                    wrap_processors=wrap_processors,
                    post_processors=post_processors,
                    max_retries=max_retries - 1,
                )
            else:
                return ChatCompletionError(
                    status_code=ResponseCodes.RESPONSE_PROCESSING_ERROR,
                    message=str(e),
                    model=agent.name,
                    request_messages=ctx.payload.messages,
                )

        return response

    @staticmethod
    def process_api_status_error(
        model_name: str,
        ctx: ProcessContext[ChatCompletionRequest],
        status_code: ResponseCodes,
        error: openai.APIStatusError,
        messages: List[Union[LLMMessage]],
    ) -> ChatCompletionError:  # pragma: no cover
        """
        Process API status error and return a ChatCompletionError object.
        """
        cc_error = ChatCompletionError(
            status_code=status_code,
            message=error.message,
            response=error.response.text if error.response else None,
            model=model_name,
            request_messages=messages,
            body=error.body if hasattr(error, "body") else None,
        )

        return cc_error

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

            if isinstance(chat_response, ChatCompletionError):
                ctx.send_error(chat_response)
                return chat_response

            reasoning = chat_response.choices[0].message.reasoning_content if chat_response.choices else ""

            if reasoning:
                ctx.send(chat_response, reason=reasoning)
            else:
                ctx.send(chat_response)
            return chat_response
        except openai.APIStatusError as e:  # pragma: no cover
            logging.error(f"Error in LLM completion: {e}")
            # Publish the error message
            error = LLMAgentHelper.process_api_status_error(
                model_name=config.model,
                ctx=ctx,
                status_code=ResponseCodes(e.status_code),
                error=e,
                messages=ctx.payload.messages,
            )

            ctx.send_error(error)
            return error
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
