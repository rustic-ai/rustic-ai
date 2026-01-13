import json
import logging
import time
from typing import List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    DiscriminatedLLMMessage,
    FinishReason,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent.llm_agent_conf import Models
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_plugin_mixin import LLMPluginMixin, build_plugins
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)

from .models import ReActStep
from .toolset import ReActToolset

logger = logging.getLogger(__name__)


DEFAULT_REACT_SYSTEM_PROMPT = """You are an AI assistant that uses the ReAct (Reasoning and Acting) pattern to solve problems.

For each step, you should:
1. **Think**: Reason about the current situation and what action to take next
2. **Act**: Call a tool if you need more information or to perform an action
3. **Observe**: Analyze the result from the tool

Continue this process until you have enough information to provide a final answer.

When you have gathered sufficient information, provide your final answer directly without calling any tools.

Important guidelines:
- Always explain your reasoning before taking an action
- Use tools when you need external information or to perform specific tasks
- If a tool returns an error, try to understand the issue and adapt your approach
- Provide clear, concise final answers based on the information gathered
"""


class ReActAgentConfig(BaseAgentProps, LLMPluginMixin):
    """
    Configuration for the ReActAgent.

    This config extends LLMPluginMixin to support the same plugin pipeline
    as LLMAgent, while adding ReAct-specific settings like max_iterations
    and toolset.

    Plugin execution for ReActAgent:

    Loop-level plugins (from LLMPluginMixin):
    - request_preprocessors: Run ONCE before the ReAct loop starts
    - llm_request_wrappers: Wrap the entire loop (pre once, post once)
    - response_postprocessors: Run ONCE after the loop completes

    Iteration-level plugins (ReAct-specific):
    - iteration_preprocessors: Run BEFORE each LLM call in the loop
    - iteration_wrappers: Wrap each individual LLM call
    - iteration_postprocessors: Run AFTER each LLM call in the loop

    Tool-level plugins (ReAct-specific):
    - tool_wrappers: Wrap each tool execution (can modify inputs/outputs, skip, handle errors)
    """

    model_config = ConfigDict(extra="ignore")

    model: Union[str, Models] = Field(description="ID of the model to use")
    """
    ID of the model to use for LLM calls.
    """

    system_prompt: Optional[str] = Field(default=None)
    """
    Custom system prompt. If not provided, uses the default ReAct prompt.
    """

    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Sampling temperature for the LLM. Higher values make output more random.
    """

    max_tokens: Optional[int] = Field(default=None, ge=1)
    """
    Maximum number of tokens to generate in each LLM response.
    """

    max_iterations: int = Field(default=10, ge=1, le=100)
    """
    Maximum number of ReAct iterations before stopping.
    """

    toolset: ReActToolset = Field(description="The toolset providing tools and execution")
    """
    The toolset that defines available tools and their execution logic.
    """

    base_url: Optional[str] = None
    """Base URL for the LLM API."""

    custom_llm_provider: Optional[str] = None
    """Custom LLM provider to use."""

    timeout: Optional[float] = None
    """Timeout for LLM API requests."""

    # Per-iteration plugins (ReAct-specific)
    iteration_preprocessors: List[RequestPreprocessor] = Field(default_factory=list)
    """
    Preprocessors that run BEFORE each LLM call within the ReAct loop.
    Use for per-step context injection, logging, etc.
    """

    iteration_wrappers: List[LLMCallWrapper] = Field(default_factory=list)
    """
    Wrappers that wrap each individual LLM call within the loop.
    The preprocess runs before each call, postprocess after each call.
    """

    iteration_postprocessors: List[ResponsePostprocessor] = Field(default_factory=list)
    """
    Postprocessors that run AFTER each LLM call within the ReAct loop.
    Use for per-step cost tracking, evaluation, logging, etc.
    """

    tool_wrappers: List[ToolCallWrapper] = Field(default_factory=list)
    """
    Wrappers that wrap each tool execution within the ReAct loop.
    Use for logging, caching, input validation, error handling, etc.
    Tool wrappers can:
    - Modify tool inputs before execution
    - Skip execution and return cached/computed results
    - Modify outputs after execution
    - Handle errors with custom logic
    - Generate additional messages
    """

    @field_validator("iteration_preprocessors", mode="before")
    @classmethod
    def _coerce_iter_preprocessors(cls, v):
        return build_plugins(v, RequestPreprocessor)

    @field_validator("iteration_wrappers", mode="before")
    @classmethod
    def _coerce_iter_wrappers(cls, v):
        return build_plugins(v, LLMCallWrapper)

    @field_validator("iteration_postprocessors", mode="before")
    @classmethod
    def _coerce_iter_postprocessors(cls, v):
        return build_plugins(v, ResponsePostprocessor)

    @field_validator("tool_wrappers", mode="before")
    @classmethod
    def _coerce_tool_wrappers(cls, v):
        return build_plugins(v, ToolCallWrapper)

    @field_validator("toolset", mode="before")
    @classmethod
    def _load_toolset(cls, v):
        """Load toolset from dict with FQCN resolution."""
        if isinstance(v, dict):
            kind = v.get("kind")
            if not kind:
                raise ValueError("toolset.kind is required for dict-based toolset configuration")
            toolset_cls = get_class_from_name(kind)
            if not issubclass(toolset_cls, ReActToolset):
                raise ValueError(f"Toolset class {toolset_cls} is not a subclass of ReActToolset")
            return toolset_cls.model_validate(v)
        elif isinstance(v, ReActToolset):
            return v
        else:
            raise ValueError("toolset must be a dict or ReActToolset instance")

    @field_serializer("toolset", mode="plain")
    def _serialize_toolset(self, toolset):
        """Serialize toolset to dict for JSON/YAML output."""
        data = toolset.model_dump()
        # Add kind for deserialization
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

        data["kind"] = get_qualified_class_name(type(toolset))
        return data

    # Fields that should not be passed to the LLM
    _non_llm_fields = {
        "max_retries",
        "request_preprocessors",
        "llm_request_wrappers",
        "response_postprocessors",
        "iteration_preprocessors",
        "iteration_wrappers",
        "iteration_postprocessors",
        "tool_wrappers",
        "max_iterations",
        "toolset",
        "system_prompt",
    }

    def has_iteration_plugins(self) -> bool:
        """Check if any per-iteration plugins are configured."""
        return bool(self.iteration_preprocessors or self.iteration_wrappers or self.iteration_postprocessors)

    def has_tool_wrappers(self) -> bool:
        """Check if any tool wrappers are configured."""
        return bool(self.tool_wrappers)

    def get_llm_params(self) -> dict:
        """
        Get the LLM parameters from the config, excluding non-LLM fields.
        """
        return self.model_dump(exclude={*self._non_llm_fields})


class ReActAgent(Agent[ReActAgentConfig]):
    """
    An agent that implements the ReAct (Reasoning and Acting) pattern.

    The ReActAgent iteratively:
    1. Calls the LLM with the current conversation and available tools
    2. If the LLM requests a tool call, executes the tool and adds the result
    3. Repeats until the LLM provides a final answer or max iterations is reached

    Plugin execution model:
    - Preprocessors wrap the entire ReAct loop (run once before loop starts)
    - Postprocessors wrap the entire ReAct loop (run once after loop ends)
    - Individual LLM calls within the loop do NOT trigger plugins

    This agent is suitable for simple, self-contained ReAct use cases where
    tools are executed synchronously within the agent. For more complex
    multi-agent scenarios, consider using the message-based approach with
    LLMAgent and separate ToolAgents.
    """

    @processor(clz=ChatCompletionRequest, depends_on=["llm"])
    def handle_chat_completion_request(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Process a ChatCompletionRequest by running the ReAct reasoning loop.

        The agent extracts the query from the last UserMessage and runs the ReAct
        loop. Any SystemMessage in the incoming request is preserved and prepended
        to the ReAct system prompt.

        The response is a ChatCompletionResponse with the reasoning trace stored in
        Choice.provider_specific_fields["react_trace"].

        Args:
            ctx: The process context containing the ChatCompletionRequest.
            llm: The LLM dependency for making completion calls.
        """
        request = ctx.payload

        try:
            result, plugin_messages = self._run_react_loop(ctx, request, llm)

            # Send plugin-generated messages first
            for msg in plugin_messages:
                ctx.send(msg)

            # Send the final ChatCompletionResponse
            ctx.send(result)

        except Exception as e:
            logger.error(f"Error in ReAct loop: {e}", exc_info=True)
            ctx.send_error(
                ChatCompletionError(
                    status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                    message=f"Error in ReAct loop: {e}",
                    model=str(self.config.model),
                    request_messages=list(request.messages),
                )
            )

    def _run_react_loop(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        incoming_request: ChatCompletionRequest,
        llm: LLM,
    ) -> tuple[ChatCompletionResponse, list]:
        """
        Execute the ReAct reasoning loop with plugin support.

        Plugins wrap the entire loop:
        - Preprocessors run once before the loop
        - Postprocessors run once on the final response

        Args:
            ctx: The process context (needed for plugin execution).
            incoming_request: The incoming ChatCompletionRequest.
            llm: The LLM to use for completions.

        Returns:
            Tuple of (ChatCompletionResponse, plugin_messages)
        """
        # Record start time for response
        start_time = int(time.time())

        # Extract system messages and user query from incoming request
        incoming_system_messages: List[SystemMessage] = []
        user_query: Optional[str] = None

        for msg in incoming_request.messages:
            if isinstance(msg, SystemMessage):
                incoming_system_messages.append(msg)
            elif isinstance(msg, UserMessage):
                # Use the last UserMessage as the query
                if isinstance(msg.content, str):
                    user_query = msg.content
                else:
                    # ArrayOfContentParts - extract text parts
                    text_parts = [p.text for p in msg.content.root if hasattr(p, "text")]
                    user_query = " ".join(text_parts)

        if not user_query:
            # No user query found - return error response
            return (
                self._build_error_response(
                    "No user message found in request",
                    start_time,
                    [],
                    0,
                ),
                [],
            )

        # Build the messages list: incoming system messages + ReAct system prompt + user query
        initial_messages: List[DiscriminatedLLMMessage] = []

        # Append incoming system messages first (preserving user context)
        for sys_msg in incoming_system_messages:
            initial_messages.append(sys_msg)

        # Append the ReAct system prompt
        initial_messages.append(SystemMessage(content=self._get_system_prompt()))

        # Append the user query
        initial_messages.append(UserMessage(content=user_query))

        # Build initial request with tools from toolset
        # Use temperature/max_tokens from incoming request if provided, else fall back to config
        initial_request = ChatCompletionRequest(
            messages=initial_messages,
            tools=self.config.toolset.chat_tools if self.config.toolset.tool_count > 0 else None,
            temperature=incoming_request.temperature or self.config.temperature,
            max_tokens=incoming_request.max_tokens or self.config.max_tokens,
        )

        # PREPROCESS (once, before loop) - create a temporary context for the helper
        prepared_request = self._preprocess_if_needed(ctx, llm, initial_request)

        # Extract messages and tools from prepared request
        messages: List[DiscriminatedLLMMessage] = list(prepared_request.messages)
        tools = prepared_request.tools

        trace: List[ReActStep] = []
        toolset = self.config.toolset
        final_response: Optional[ChatCompletionResponse] = None
        iterations_completed = 0
        total_usage = CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

        all_iteration_messages: list = []  # Accumulate messages from iteration plugins

        for iteration in range(self.config.max_iterations):
            iterations_completed = iteration + 1

            # Build request for this iteration
            iteration_request = ChatCompletionRequest(
                messages=messages,
                tools=tools,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # ITERATION PREPROCESS (before each LLM call)
            iteration_request = self._preprocess_iteration_if_needed(ctx, llm, iteration_request, iteration)

            # Call LLM
            response = self._call_llm_direct(llm, iteration_request)

            if isinstance(response, str):
                # Error occurred - return error response
                return (
                    self._build_error_response(
                        response,
                        start_time,
                        trace,
                        iterations_completed,
                    ),
                    all_iteration_messages,
                )

            # Accumulate usage statistics
            if response.usage:
                total_usage = CompletionUsage(
                    prompt_tokens=total_usage.prompt_tokens + response.usage.prompt_tokens,
                    completion_tokens=total_usage.completion_tokens + response.usage.completion_tokens,
                    total_tokens=total_usage.total_tokens + response.usage.total_tokens,
                )

            # ITERATION POSTPROCESS (after each LLM call)
            iter_messages = self._postprocess_iteration_if_needed(ctx, llm, iteration_request, response, iteration)
            all_iteration_messages.extend(iter_messages)

            choice = response.choices[0]
            assistant_message = choice.message

            # Add assistant response to messages
            messages.append(assistant_message)

            # Check if we have tool calls
            if not assistant_message.tool_calls:
                # No tool calls - this is the final answer
                final_response = response
                break

            # Process each tool call
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    tool_result = f"Error parsing tool arguments: {e}"
                    trace.append(
                        ReActStep(
                            thought=assistant_message.content,
                            action=tool_name,
                            action_input={"raw": tool_call.function.arguments},
                            observation=tool_result,
                        )
                    )
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=tool_result,
                        )
                    )
                    continue

                # Execute tool with wrapper pipeline
                tool_result, tool_messages = self._execute_tool_with_wrappers(
                    ctx, tool_name, tool_args, toolset, assistant_message.content
                )
                all_iteration_messages.extend(tool_messages)

                # Record in trace
                trace.append(
                    ReActStep(
                        thought=assistant_message.content,
                        action=tool_name,
                        action_input=tool_args,
                        observation=tool_result,
                    )
                )

                # Add tool result to messages
                messages.append(
                    ToolMessage(
                        tool_call_id=tool_call.id,
                        content=tool_result,
                    )
                )

        # POSTPROCESS (once, after loop)
        loop_plugin_messages = self._postprocess_if_needed(ctx, llm, prepared_request, final_response)

        # Combine iteration messages with loop-level plugin messages
        all_plugin_messages = all_iteration_messages + loop_plugin_messages

        # Build final response as ChatCompletionResponse
        if final_response:
            return (
                self._build_success_response(
                    answer=final_response.choices[0].message.content or "",
                    start_time=start_time,
                    trace=trace,
                    iterations=iterations_completed,
                    usage=total_usage,
                ),
                all_plugin_messages,
            )
        else:
            # Max iterations reached
            return (
                self._build_max_iterations_response(
                    start_time=start_time,
                    trace=trace,
                    iterations=self.config.max_iterations,
                    usage=total_usage,
                ),
                all_plugin_messages,
            )

    def _preprocess_if_needed(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        request: ChatCompletionRequest,
    ) -> ChatCompletionRequest:
        """Run preprocessing if plugins are configured."""
        if not self.config.has_plugins():
            return request

        return LLMAgentHelper.preprocess_request(
            agent=self,
            config=self.config,
            llm=llm,
            ctx=ctx,
            request=request,
            llm_params=self.config.get_llm_params(),
        )

    def _postprocess_if_needed(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        request: ChatCompletionRequest,
        response: Optional[ChatCompletionResponse],
    ) -> list:
        """Run postprocessing if plugins are configured and we have a response."""
        if not self.config.has_plugins() or response is None:
            return []

        return LLMAgentHelper.postprocess_response(
            agent=self,
            config=self.config,
            llm=llm,
            ctx=ctx,
            final_request=request,
            response=response,
        )

    def _preprocess_iteration_if_needed(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        request: ChatCompletionRequest,
        iteration: int,
    ) -> ChatCompletionRequest:
        """Run per-iteration preprocessing if iteration plugins are configured."""
        if not self.config.has_iteration_plugins():
            return request

        # Use a temporary config-like object with just the iteration plugins
        return LLMAgentHelper.preprocess_request(
            agent=self,
            config=self._iteration_plugin_config(),
            llm=llm,
            ctx=ctx,
            request=request,
            llm_params=self.config.get_llm_params(),
        )

    def _postprocess_iteration_if_needed(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
        iteration: int,
    ) -> list:
        """Run per-iteration postprocessing if iteration plugins are configured."""
        if not self.config.has_iteration_plugins():
            return []

        return LLMAgentHelper.postprocess_response(
            agent=self,
            config=self._iteration_plugin_config(),
            llm=llm,
            ctx=ctx,
            final_request=request,
            response=response,
        )

    def _iteration_plugin_config(self):
        """
        Create a config-like object with iteration plugins mapped to standard fields.

        This allows us to reuse LLMAgentHelper methods which expect the standard
        plugin field names (request_preprocessors, llm_request_wrappers, etc.).
        """

        class _IterationPluginConfig:
            def __init__(self, config: ReActAgentConfig):
                self.request_preprocessors = config.iteration_preprocessors
                self.llm_request_wrappers = config.iteration_wrappers
                self.response_postprocessors = config.iteration_postprocessors
                self.max_retries = 0  # No retries at iteration level

        return _IterationPluginConfig(self.config)

    def _get_system_prompt(self) -> str:
        """Get the system prompt, using custom or default."""
        if self.config.system_prompt:
            return self.config.system_prompt
        return DEFAULT_REACT_SYSTEM_PROMPT

    def _build_success_response(
        self,
        answer: str,
        start_time: int,
        trace: List[ReActStep],
        iterations: int,
        usage: Optional[CompletionUsage] = None,
    ) -> ChatCompletionResponse:
        """
        Build a successful ChatCompletionResponse with react_trace in provider_specific_fields.

        Args:
            answer: The final answer content.
            start_time: Unix timestamp when the loop started.
            trace: The reasoning trace of ReActSteps.
            iterations: Number of iterations completed.
            usage: Aggregated token usage statistics.

        Returns:
            ChatCompletionResponse with the answer and trace metadata.
        """
        return ChatCompletionResponse(
            id=f"react-{uuid.uuid4().hex[:12]}",
            created=start_time,
            model=str(self.config.model),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content=answer),
                    finish_reason=FinishReason.stop,
                    provider_specific_fields={
                        "react_trace": [step.model_dump() for step in trace],
                        "iterations": iterations,
                    },
                )
            ],
            usage=usage if usage and usage.total_tokens > 0 else None,
        )

    def _build_error_response(
        self,
        error_message: str,
        start_time: int,
        trace: List[ReActStep],
        iterations: int,
    ) -> ChatCompletionResponse:
        """
        Build an error ChatCompletionResponse with react_trace in provider_specific_fields.

        Args:
            error_message: The error message.
            start_time: Unix timestamp when the loop started.
            trace: The reasoning trace of ReActSteps up to the error.
            iterations: Number of iterations completed before error.

        Returns:
            ChatCompletionResponse with error info in provider_specific_fields.
        """
        return ChatCompletionResponse(
            id=f"react-{uuid.uuid4().hex[:12]}",
            created=start_time,
            model=str(self.config.model),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content=error_message),
                    finish_reason=FinishReason.stop,
                    provider_specific_fields={
                        "react_trace": [step.model_dump() for step in trace],
                        "iterations": iterations,
                        "error": error_message,
                        "success": False,
                    },
                )
            ],
        )

    def _build_max_iterations_response(
        self,
        start_time: int,
        trace: List[ReActStep],
        iterations: int,
        usage: Optional[CompletionUsage] = None,
    ) -> ChatCompletionResponse:
        """
        Build a ChatCompletionResponse for when max iterations is reached.

        Args:
            start_time: Unix timestamp when the loop started.
            trace: The reasoning trace of ReActSteps.
            iterations: Number of iterations (max_iterations).
            usage: Aggregated token usage statistics.

        Returns:
            ChatCompletionResponse with finish_reason=length indicating truncation.
        """
        return ChatCompletionResponse(
            id=f"react-{uuid.uuid4().hex[:12]}",
            created=start_time,
            model=str(self.config.model),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content="Maximum iterations reached. Unable to complete the task."),
                    finish_reason=FinishReason.length,  # Indicates truncation
                    provider_specific_fields={
                        "react_trace": [step.model_dump() for step in trace],
                        "iterations": iterations,
                        "error": "Max iterations reached",
                        "success": False,
                    },
                )
            ],
            usage=usage if usage and usage.total_tokens > 0 else None,
        )

    def _call_llm(
        self,
        llm: LLM,
        messages: List[DiscriminatedLLMMessage],
        tools: Optional[list] = None,
    ) -> Union[ChatCompletionResponse, str]:
        """
        Call the LLM with the given messages and tools.

        Args:
            llm: The LLM to use.
            messages: The conversation messages.
            tools: Optional tools list (uses toolset if not provided).

        Returns:
            ChatCompletionResponse on success, error string on failure.
        """
        if tools is None:
            tools = self.config.toolset.chat_tools if self.config.toolset.tool_count > 0 else None

        request = ChatCompletionRequest(
            messages=messages,
            tools=tools,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        return self._call_llm_direct(llm, request)

    def _call_llm_direct(
        self,
        llm: LLM,
        request: ChatCompletionRequest,
    ) -> Union[ChatCompletionResponse, str]:
        """
        Call the LLM with a pre-built request.

        Args:
            llm: The LLM to use.
            request: The chat completion request.

        Returns:
            ChatCompletionResponse on success, error string on failure.
        """
        try:
            response = llm.completion(request, self.config.model)
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return f"LLM call failed: {e}"

    def _execute_tool_with_wrappers(
        self,
        ctx: ProcessContext,
        tool_name: str,
        tool_args: dict,
        toolset: ReActToolset,
        thought: Optional[str] = None,
    ) -> tuple[str, list]:
        """
        Execute a tool with the wrapper pipeline.

        Tool wrappers allow:
        - Preprocessing: Modify inputs or skip execution (return cached result)
        - Postprocessing: Modify outputs and generate messages
        - Error handling: Custom error recovery

        Args:
            ctx: The process context.
            tool_name: Name of the tool to execute.
            tool_args: Tool arguments as a dict.
            toolset: The toolset containing the tool.
            thought: Optional thought/reasoning from the LLM.

        Returns:
            Tuple of (tool_output, plugin_messages)
        """
        plugin_messages: list = []

        # Get tool spec
        toolspec = toolset.get_toolspec(tool_name)
        if not toolspec:
            return f"Error: Unknown tool '{tool_name}'", plugin_messages

        # Parse arguments into BaseModel
        try:
            parsed_args = toolspec.parse_args(tool_args)
        except Exception as e:
            return f"Error parsing tool arguments: {e}", plugin_messages

        # Run preprocess on all wrappers
        current_args = parsed_args
        for wrapper in self.config.tool_wrappers:
            try:
                result = wrapper.preprocess(
                    agent=self,
                    ctx=ctx,
                    tool_name=tool_name,
                    tool_input=current_args,
                )
                if isinstance(result, ToolSkipResult):
                    # Wrapper wants to skip execution
                    tool_output = result.output
                    # Still run postprocessors with the skipped result
                    return self._run_tool_postprocessors(ctx, tool_name, current_args, tool_output, plugin_messages)
                else:
                    # Continue with modified args
                    current_args = result
            except Exception as e:
                logger.warning(f"Tool preprocess error in {wrapper.__class__.__name__}: {e}")
                # Continue with current args on preprocess error

        # Execute the tool
        try:
            tool_output = toolset.execute(tool_name, current_args)
        except Exception as e:
            logger.warning(f"Error executing tool {tool_name}: {e}")
            # Try error handlers
            handled_output = self._run_tool_error_handlers(ctx, tool_name, current_args, e)
            if handled_output is not None:
                tool_output = handled_output
            else:
                tool_output = f"Error executing tool: {e}"

        # Run postprocessors
        return self._run_tool_postprocessors(ctx, tool_name, current_args, tool_output, plugin_messages)

    def _run_tool_postprocessors(
        self,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
        plugin_messages: list,
    ) -> tuple[str, list]:
        """
        Run tool postprocessors on the output.

        Args:
            ctx: The process context.
            tool_name: Name of the tool.
            tool_input: The parsed tool input.
            tool_output: The tool output string.
            plugin_messages: List to accumulate messages.

        Returns:
            Tuple of (final_output, plugin_messages)
        """
        current_output = tool_output
        for wrapper in self.config.tool_wrappers:
            try:
                result: ToolCallResult = wrapper.postprocess(
                    agent=self,
                    ctx=ctx,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=current_output,
                )
                current_output = result.output
                if result.messages:
                    plugin_messages.extend(result.messages)
            except Exception as e:
                logger.warning(f"Tool postprocess error in {wrapper.__class__.__name__}: {e}")
                # Continue with current output on postprocess error

        return current_output, plugin_messages

    def _run_tool_error_handlers(
        self,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        error: Exception,
    ) -> Optional[str]:
        """
        Run tool error handlers to potentially recover from an error.

        Args:
            ctx: The process context.
            tool_name: Name of the tool.
            tool_input: The parsed tool input.
            error: The exception that occurred.

        Returns:
            A string output if error was handled, None otherwise.
        """
        for wrapper in self.config.tool_wrappers:
            try:
                result = wrapper.on_error(
                    agent=self,
                    ctx=ctx,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    error=error,
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(f"Tool error handler failed in {wrapper.__class__.__name__}: {e}")

        return None
