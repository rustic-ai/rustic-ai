from dataclasses import dataclass, field
import json
import logging
import time
from typing import List, Literal, Optional, Union
import uuid

import openai
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_serializer,
    field_validator,
)

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionTool,
    ChatCompletionToolChoiceOption,
    Choice,
    CompletionUsage,
    DiscriminatedLLMMessage,
    FinishReason,
    ResponseCodes,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
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
from .toolset import (
    ReActSkillSpec,
    ReActToolOutcome,
    ReActToolset,
    ToolOutcomeDisposition,
)

logger = logging.getLogger(__name__)


DEFAULT_REACT_SYSTEM_PROMPT = """Use the available tools for exact or verifiable results.

- Call tools directly without narrating a plan.
- For multi-part requests, identify every requested result and complete each one.
- For dependent steps, use the exact result of the previous tool call as the next input.
- Call each required tool once. After an error, make at most one corrected call and never repeat identical arguments.
- In the final answer, include every requested result and preserve tool-returned values, dates, units, timezones, and
  precision. Round only when requested.
- Ask for clarification when required information is missing or ambiguous. Never replace an unavailable tool result
  with a guess.
"""

SKILL_SELECTOR_TOOL = "activate_tool_skill"


@dataclass
class _ReActLoopState:
    """Mutable state shared by the small steps of a ReAct execution loop."""

    messages: List[DiscriminatedLLMMessage]
    tools: Optional[List[ChatCompletionTool]]
    safe_handling: bool
    trace: List[ReActStep] = field(default_factory=list)
    final_response: Optional[ChatCompletionResponse] = None
    iterations_completed: int = 0
    total_usage: CompletionUsage = field(
        default_factory=lambda: CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    )
    executed_calls: dict[str, ReActToolOutcome | None] = field(default_factory=dict)
    failure_attempts: dict[tuple[str, str], int] = field(default_factory=dict)
    verified_results: list[dict[str, str]] = field(default_factory=list)
    unresolved_failures: list[dict[str, str]] = field(default_factory=list)
    last_interpreted_tool: Optional[str] = None
    policy_termination: Optional[str] = None
    active_skill_names: set[str] = field(default_factory=set)
    domain_tool_required: bool = False
    disclosure_expanded: bool = False
    plugin_messages: list = field(default_factory=list)


class ActivateToolSkillArgs(BaseModel):
    """Activate one related tool group for progressive disclosure."""

    model_config = ConfigDict(extra="forbid")

    skill: str = Field(description="One skill needed for the next tool action.")


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

    model: Optional[Union[str, Models]] = Field(description="ID of the model to use", default=None, examples=["gpt-5"])
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

    failure_handling: Literal["safe", "legacy"] = Field(default="safe")
    """Safe mode bounds retries and grounds failures; legacy preserves the unrestricted loop."""

    tool_disclosure: Literal["all", "skills"] = Field(default="all")
    """Expose all tools immediately or progressively disclose configured skill groups."""

    skill_activation_followup: Literal["auto", "required"] = Field(default="auto")
    """Optionally require one disclosed domain-tool call immediately after activating a skill."""

    skill_activation_observation: Literal["standard", "explicit"] = Field(default="standard")
    """Control whether activation results explicitly distinguish disclosure from task completion."""

    skill_disclosure_progression: Literal["sticky", "expand_after_first_success"] = Field(default="sticky")
    """Keep activated groups scoped, or expose the full catalog after the first successful domain action."""

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
        "failure_handling",
        "tool_disclosure",
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

        except openai.APIConnectionError as e:
            logger.error("Provider connection error in ReAct loop: %s", e, exc_info=True)
            error = ChatCompletionError(
                status_code=(
                    ResponseCodes.API_TIMEOUT_ERROR
                    if isinstance(e, openai.APITimeoutError)
                    else ResponseCodes.API_CONNECTION_ERROR
                ),
                message=str(e),
                model=str(self.config.model) if self.config.model else self.name,
                request_messages=list(request.messages),
            )
            ctx.send_error(error)
        except openai.APIStatusError as e:
            logger.error("Provider error in ReAct loop: %s", e, exc_info=True)
            error = ChatCompletionError(
                status_code=ResponseCodes(e.status_code),
                message=e.message,
                response=e.response.text if e.response else None,
                model=str(self.config.model) if self.config.model else self.name,
                request_messages=list(request.messages),
                body=e.body if hasattr(e, "body") else None,
            )
            ctx.send_error(error)
        except Exception as e:
            logger.error(f"Error in ReAct loop: {e}", exc_info=True)
            ctx.send_error(
                ChatCompletionError(
                    status_code=ResponseCodes.INTERNAL_SERVER_ERROR,
                    message=f"Error in ReAct loop: {e}",
                    model=str(self.config.model) if self.config.model else None,
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
        start_time = int(time.time())
        self.config.toolset.bind_agent_context(
            org_id=self.get_organization(),
            guild_id=self.guild_id,
            agent_id=self.id,
        )
        all_preprocessors = self.config.request_preprocessors + self.config.iteration_preprocessors
        self.config.toolset.validate_plugins(
            request_preprocessors=all_preprocessors,
            tool_wrappers=self.config.tool_wrappers,
        )
        incoming_system_messages: List[SystemMessage] = []
        user_query: Optional[str] = None
        for msg in incoming_request.messages:
            if isinstance(msg, SystemMessage):
                incoming_system_messages.append(msg)
            elif isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    user_query = msg.content
                else:
                    text_parts = [p.text for p in msg.content.root if hasattr(p, "text")]
                    user_query = " ".join(text_parts)
        if not user_query:
            return (
                self._build_error_response(
                    "No user message found in request",
                    start_time,
                    [],
                    0,
                ),
                [],
            )

        skill_specs = self.config.toolset.get_skill_specs() if self.config.tool_disclosure == "skills" else []
        self._validate_skill_specs(self.config.toolset, skill_specs)
        skill_mode = bool(skill_specs)
        initial_messages: List[DiscriminatedLLMMessage] = list(incoming_system_messages)
        initial_messages.append(SystemMessage(content=self._get_system_prompt()))
        initial_messages.append(UserMessage(content=user_query))
        initial_tools = (
            [self._skill_selector_spec(skill_specs).chat_tool]
            if skill_mode
            else (self.config.toolset.chat_tools if self.config.toolset.tool_count > 0 else None)
        )
        initial_request = ChatCompletionRequest(
            messages=initial_messages,
            tools=initial_tools,
            temperature=incoming_request.temperature or self.config.temperature,
            max_tokens=incoming_request.max_tokens or self.config.max_tokens,
        )
        prepared_request = self._preprocess_if_needed(ctx, llm, initial_request)
        state = _ReActLoopState(
            messages=list(prepared_request.messages),
            tools=prepared_request.tools,
            safe_handling=self.config.failure_handling == "safe",
        )
        error = self._run_react_iterations(ctx, llm, skill_specs, state)
        if error:
            return (
                self._build_error_response(error, start_time, state.trace, state.iterations_completed),
                state.plugin_messages,
            )

        loop_plugin_messages = self._postprocess_if_needed(ctx, llm, prepared_request, state.final_response)
        all_plugin_messages = state.plugin_messages + loop_plugin_messages
        return (self._finalize_react_loop(state, start_time), all_plugin_messages)

    def _run_react_iterations(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        skill_specs: List[ReActSkillSpec],
        state: _ReActLoopState,
    ) -> Optional[str]:
        """Run model iterations, mutating shared loop state until completion."""
        for iteration in range(self.config.max_iterations):
            state.iterations_completed = iteration + 1
            advertised_tool_names = {
                tool.function.name for tool in (state.tools or []) if getattr(tool, "function", None) is not None
            }
            iteration_request = self._build_react_iteration_request(state)
            iteration_request = self._preprocess_iteration_if_needed(ctx, llm, iteration_request, iteration)
            response = self._call_llm_direct(llm, iteration_request)
            if response.usage:
                state.total_usage = CompletionUsage(
                    prompt_tokens=state.total_usage.prompt_tokens + response.usage.prompt_tokens,
                    completion_tokens=state.total_usage.completion_tokens + response.usage.completion_tokens,
                    total_tokens=state.total_usage.total_tokens + response.usage.total_tokens,
                )
            iter_messages = self._postprocess_iteration_if_needed(ctx, llm, iteration_request, response, iteration)
            state.plugin_messages.extend(iter_messages)
            assistant_message = response.choices[0].message
            state.messages.append(assistant_message)
            if not assistant_message.tool_calls:
                state.final_response = response
                if state.safe_handling and state.unresolved_failures:
                    state.policy_termination = "unresolved_tool_failure"
                break
            for tool_call in assistant_message.tool_calls:
                self._process_react_tool_call(
                    ctx, assistant_message, tool_call, advertised_tool_names, skill_specs, state
                )
            if state.policy_termination:
                break
        return None

    def _build_react_iteration_request(self, state: _ReActLoopState) -> ChatCompletionRequest:
        """Build the next model request from current disclosure state."""
        iteration_tools = state.tools
        tool_choice = None
        if state.domain_tool_required and self.config.skill_activation_followup == "required":
            iteration_tools = [
                tool
                for tool in (state.tools or [])
                if getattr(getattr(tool, "function", None), "name", None) != SKILL_SELECTOR_TOOL
            ]
            tool_choice = ChatCompletionToolChoiceOption.required
        return ChatCompletionRequest(
            messages=state.messages,
            tools=iteration_tools,
            tool_choice=tool_choice,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def _process_react_tool_call(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        advertised_tool_names: set[str],
        skill_specs: List[ReActSkillSpec],
        state: _ReActLoopState,
    ) -> None:
        """Route one model tool call to the appropriate bounded handler."""
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as error:
            self._handle_invalid_tool_arguments(assistant_message, tool_call, tool_name, error, state)
            return
        if skill_specs and tool_name == SKILL_SELECTOR_TOOL:
            self._handle_skill_activation(assistant_message, tool_call, tool_args, skill_specs, state)
            return
        if skill_specs and tool_name not in advertised_tool_names:
            self._handle_undisclosed_tool(assistant_message, tool_call, tool_name, tool_args, state)
            return
        fingerprint = self._tool_call_fingerprint(tool_name, tool_args)
        if state.safe_handling and fingerprint in state.executed_calls:
            self._handle_duplicate_tool_call(assistant_message, tool_call, tool_name, tool_args, fingerprint, state)
            return
        self._handle_executed_tool_call(
            ctx, assistant_message, tool_call, tool_name, tool_args, fingerprint, skill_specs, state
        )

    def _handle_invalid_tool_arguments(
        self,
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        tool_name: str,
        error: json.JSONDecodeError,
        state: _ReActLoopState,
    ) -> None:
        tool_result = self._structured_tool_error(
            "invalid_arguments",
            f"Tool arguments are not valid JSON: {self._bounded_error(error)}",
        )
        outcome = ReActToolOutcome(
            disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
            code="invalid_arguments",
            message="Tool arguments were not valid JSON.",
        )
        attempt = self._record_failure_attempt(state.failure_attempts, tool_name, outcome)
        state.trace.append(
            ReActStep(
                thought=assistant_message.content,
                action=tool_name,
                action_input={"raw": tool_call.function.arguments},
                observation=tool_result,
                outcome=outcome.disposition.value,
                error_code=outcome.code,
                attempt=attempt,
                model_round=state.iterations_completed,
            )
        )
        state.messages.append(ToolMessage(tool_call_id=tool_call.id, content=tool_result))
        self._append_failure(state.unresolved_failures, tool_name, outcome)
        state.last_interpreted_tool = tool_name
        if state.safe_handling and attempt >= 2:
            state.policy_termination = "tool_retry_exhausted"

    def _handle_skill_activation(
        self,
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        tool_args: dict,
        skill_specs: List[ReActSkillSpec],
        state: _ReActLoopState,
    ) -> None:
        tool_name = tool_call.function.name
        result, outcome, activated = self._activate_skill(tool_args, skill_specs, state.active_skill_names)
        if activated:
            state.active_skill_names.add(activated)
            state.tools = self._disclosed_tools(skill_specs, state.active_skill_names)
            state.domain_tool_required = True
        attempt = 1
        if outcome.disposition != ToolOutcomeDisposition.SUCCESS:
            attempt = self._record_failure_attempt(state.failure_attempts, tool_name, outcome)
        state.trace.append(
            ReActStep(
                thought=assistant_message.content,
                action=tool_name,
                action_input=tool_args if isinstance(tool_args, dict) else {"raw": tool_args},
                observation=result,
                outcome=outcome.disposition.value,
                error_code=outcome.code,
                attempt=attempt,
                executed=False,
                model_round=state.iterations_completed,
            )
        )
        state.messages.append(ToolMessage(tool_call_id=tool_call.id, content=result))
        if outcome.disposition == ToolOutcomeDisposition.SUCCESS:
            self._resolve_latest_failure(state.unresolved_failures, tool_name)
            return
        self._append_failure(state.unresolved_failures, tool_name, outcome)
        if state.safe_handling and attempt >= 2:
            state.policy_termination = "tool_retry_exhausted"

    def _handle_undisclosed_tool(
        self,
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        tool_name: str,
        tool_args: dict,
        state: _ReActLoopState,
    ) -> None:
        tool_result = self._structured_tool_error(
            "tool_not_disclosed",
            "This tool is not available yet. Activate its skill, then call the tool in a later round.",
        )
        outcome = ReActToolOutcome(
            disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
            code="tool_not_disclosed",
            message="The tool was called before it was disclosed.",
        )
        attempt = self._record_failure_attempt(state.failure_attempts, tool_name, outcome)
        state.trace.append(
            ReActStep(
                thought=assistant_message.content,
                action=tool_name,
                action_input=tool_args,
                observation=tool_result,
                outcome=outcome.disposition.value,
                error_code=outcome.code,
                attempt=attempt,
                executed=False,
                model_round=state.iterations_completed,
            )
        )
        state.messages.append(ToolMessage(tool_call_id=tool_call.id, content=tool_result))
        self._append_failure(state.unresolved_failures, tool_name, outcome)
        state.last_interpreted_tool = tool_name
        if state.safe_handling and attempt >= 2:
            state.policy_termination = "tool_retry_exhausted"

    def _handle_duplicate_tool_call(
        self,
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        tool_name: str,
        tool_args: dict,
        fingerprint: str,
        state: _ReActLoopState,
    ) -> None:
        previous_outcome = state.executed_calls[fingerprint]
        tool_result = self._structured_tool_error(
            "duplicate_tool_call",
            "This exact tool call was already executed; use its existing observation.",
        )
        outcome = ReActToolOutcome(
            disposition=ToolOutcomeDisposition.TERMINAL_ERROR,
            code="duplicate_tool_call",
            message="An identical tool call was suppressed.",
        )
        previous_succeeded = (
            previous_outcome is not None and previous_outcome.disposition == ToolOutcomeDisposition.SUCCESS
        )
        state.trace.append(
            ReActStep(
                thought=assistant_message.content,
                action=tool_name,
                action_input=tool_args,
                observation=tool_result,
                outcome=outcome.disposition.value,
                error_code=outcome.code,
                attempt=2,
                executed=False,
                model_round=state.iterations_completed,
            )
        )
        state.messages.append(ToolMessage(tool_call_id=tool_call.id, content=tool_result))
        if not previous_succeeded:
            self._append_failure(state.unresolved_failures, tool_name, outcome)
        state.policy_termination = "duplicate_tool_call"
        state.last_interpreted_tool = tool_name

    def _handle_executed_tool_call(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        assistant_message: AssistantMessage,
        tool_call: ChatCompletionMessageToolCall,
        tool_name: str,
        tool_args: dict,
        fingerprint: str,
        skill_specs: List[ReActSkillSpec],
        state: _ReActLoopState,
    ) -> None:
        toolset = self.config.toolset
        tool_result, tool_messages, outcome = self._execute_tool_with_wrappers(
            ctx, tool_name, tool_args, toolset, assistant_message.content
        )
        state.domain_tool_required = False
        state.plugin_messages.extend(tool_messages)
        state.executed_calls[fingerprint] = outcome
        attempt = 1
        if outcome and outcome.disposition != ToolOutcomeDisposition.SUCCESS:
            attempt = self._record_failure_attempt(state.failure_attempts, tool_name, outcome)
        state.trace.append(
            ReActStep(
                thought=assistant_message.content,
                action=tool_name,
                action_input=tool_args,
                observation=tool_result,
                outcome=outcome.disposition.value if outcome else None,
                error_code=outcome.code if outcome else None,
                attempt=attempt,
                model_round=state.iterations_completed,
            )
        )
        state.messages.append(ToolMessage(tool_call_id=tool_call.id, content=tool_result))
        if self._should_expand_disclosure(skill_specs, outcome, state):
            state.tools = toolset.chat_tools if toolset.tool_count > 0 else None
            state.disclosure_expanded = True
        self._record_tool_outcome(tool_name, outcome, attempt, state)

    def _should_expand_disclosure(
        self,
        skill_specs: List[ReActSkillSpec],
        outcome: Optional[ReActToolOutcome],
        state: _ReActLoopState,
    ) -> bool:
        return bool(
            skill_specs
            and not state.disclosure_expanded
            and self.config.skill_disclosure_progression == "expand_after_first_success"
            and (outcome is None or outcome.disposition == ToolOutcomeDisposition.SUCCESS)
        )

    def _record_tool_outcome(
        self,
        tool_name: str,
        outcome: Optional[ReActToolOutcome],
        attempt: int,
        state: _ReActLoopState,
    ) -> None:
        if not state.safe_handling or outcome is None:
            state.last_interpreted_tool = None
            return
        if outcome.disposition == ToolOutcomeDisposition.SUCCESS:
            if outcome.verified_summary:
                state.verified_results.append({"tool": tool_name, "summary": outcome.verified_summary})
            if state.last_interpreted_tool == tool_name:
                self._resolve_latest_failure(state.unresolved_failures, tool_name)
            state.last_interpreted_tool = tool_name
            return
        self._append_failure(state.unresolved_failures, tool_name, outcome)
        state.last_interpreted_tool = tool_name
        if outcome.disposition == ToolOutcomeDisposition.CLARIFICATION_REQUIRED:
            state.policy_termination = "clarification_required"
        elif outcome.disposition == ToolOutcomeDisposition.TERMINAL_ERROR:
            state.policy_termination = "tool_failure"
        elif attempt >= 2:
            state.policy_termination = "tool_retry_exhausted"

    def _finalize_react_loop(self, state: _ReActLoopState, start_time: int) -> ChatCompletionResponse:
        """Convert completed loop state into the public chat response."""
        if state.policy_termination:
            return self._build_policy_response(
                start_time=start_time,
                trace=state.trace,
                iterations=state.iterations_completed,
                usage=state.total_usage,
                termination_reason=state.policy_termination,
                verified_results=state.verified_results,
                unresolved_failures=state.unresolved_failures,
            )
        if state.final_response:
            return self._build_success_response(
                answer=state.final_response.choices[0].message.content or "",
                start_time=start_time,
                trace=state.trace,
                iterations=state.iterations_completed,
                usage=state.total_usage,
                termination_reason="completed",
            )
        if state.safe_handling and (state.verified_results or state.unresolved_failures):
            return self._build_policy_response(
                start_time=start_time,
                trace=state.trace,
                iterations=self.config.max_iterations,
                usage=state.total_usage,
                termination_reason="max_iterations",
                verified_results=state.verified_results,
                unresolved_failures=state.unresolved_failures,
            )
        return self._build_max_iterations_response(
            start_time=start_time,
            trace=state.trace,
            iterations=self.config.max_iterations,
            usage=state.total_usage,
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

    @staticmethod
    def _skill_selector_spec(skills: List[ReActSkillSpec]) -> ToolSpec:
        skill_names = tuple(skill.name for skill in skills)
        skill_type = Literal.__getitem__(skill_names)
        args_model = create_model(
            "AvailableToolSkillArgs",
            __base__=ActivateToolSkillArgs,
            skill=(skill_type, Field(description="One available skill needed for the next tool action.")),
        )
        descriptions = "; ".join(
            f"{skill.name}: {skill.description}"
            + (f" Examples: {', '.join(skill.examples)}." if skill.examples else "")
            for skill in skills
        )
        return ToolSpec(
            name=SKILL_SELECTOR_TOOL,
            description=(
                "Activate exactly one skill needed for the next tool action. Its tools become available after this "
                "call. Call this selector again later if another step needs a different skill; do not predict or "
                "activate every skill upfront. You may make separate activation calls in the same response for "
                "independent subtasks. Do not activate a skill when no tool is needed. "
                f"Available skills: {descriptions}"
            ),
            parameter_class=args_model,
        )

    @staticmethod
    def _validate_skill_specs(toolset: ReActToolset, skills: List[ReActSkillSpec]) -> None:
        if not skills:
            return
        if SKILL_SELECTOR_TOOL in toolset.tool_names:
            raise ValueError(f"Tool name {SKILL_SELECTOR_TOOL!r} is reserved for progressive disclosure")
        names = [skill.name for skill in skills]
        if len(names) != len(set(names)):
            raise ValueError("ReAct skill names must be unique")
        known_tools = set(toolset.tool_names)
        covered_tools: set[str] = set()
        for skill in skills:
            unknown = set(skill.tool_names) - known_tools
            if unknown:
                raise ValueError(f"Skill {skill.name!r} references unknown tools: {sorted(unknown)}")
            covered_tools.update(skill.tool_names)
        uncovered = known_tools - covered_tools
        if uncovered:
            raise ValueError(f"Progressive disclosure metadata does not cover tools: {sorted(uncovered)}")

    def _disclosed_tools(
        self,
        skills: List[ReActSkillSpec],
        active_names: set[str],
    ) -> List:
        selected_tools = {tool_name for skill in skills if skill.name in active_names for tool_name in skill.tool_names}
        tools = [self._skill_selector_spec(skills).chat_tool]
        tools.extend(spec.chat_tool for spec in self.config.toolset.get_toolspecs() if spec.name in selected_tools)
        return tools

    def _activate_skill(
        self,
        arguments: object,
        skills: List[ReActSkillSpec],
        active_names: set[str],
    ) -> tuple[str, ReActToolOutcome, Optional[str]]:
        known = {skill.name: skill for skill in skills}
        try:
            parsed = ActivateToolSkillArgs.model_validate(arguments)
        except ValidationError as exc:
            result = self._structured_tool_error("invalid_skill_activation", self._validation_error_message(exc))
            return (
                result,
                ReActToolOutcome(
                    disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
                    code="invalid_skill_activation",
                    message="Skill activation arguments are invalid.",
                ),
                None,
            )
        if parsed.skill not in known:
            result = self._structured_tool_error(
                "unknown_skill",
                f"Unknown skill: {parsed.skill}. Available: {', '.join(sorted(known))}.",
            )
            return (
                result,
                ReActToolOutcome(
                    disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
                    code="unknown_skill",
                    message="The requested skill does not exist.",
                ),
                None,
            )
        if parsed.skill in active_names:
            result = self._structured_tool_error(
                "already_active",
                "That skill is already active; use its exposed tools or activate a different skill.",
            )
            return (
                result,
                ReActToolOutcome(
                    disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
                    code="already_active",
                    message="The requested skill is already active.",
                ),
                None,
            )
        activated = known[parsed.skill]
        active_after = active_names | {parsed.skill}
        available_tools = [
            tool_name for skill in skills if skill.name in active_after for tool_name in skill.tool_names
        ]
        payload = {
            "status": "ok",
            "activated_skill": parsed.skill,
            "active_skills": sorted(active_after),
            "available_tools": available_tools,
            "instructions": activated.instructions,
        }
        if self.config.skill_activation_observation == "explicit":
            payload["next_action"] = (
                "Activation only disclosed tools; it did not answer the user. "
                "Call one available_tools function now before answering."
            )
        return (
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
            ReActToolOutcome(disposition=ToolOutcomeDisposition.SUCCESS),
            parsed.skill,
        )

    def _build_success_response(
        self,
        answer: str,
        start_time: int,
        trace: List[ReActStep],
        iterations: int,
        usage: Optional[CompletionUsage] = None,
        termination_reason: str = "completed",
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
                        "success": True,
                        "termination_reason": termination_reason,
                        "unresolved_tool_failures": [],
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
                        "termination_reason": "llm_error",
                        "unresolved_tool_failures": [],
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
                        "termination_reason": "max_iterations",
                        "unresolved_tool_failures": [],
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
    ) -> ChatCompletionResponse:
        """
        Call the LLM with the given messages and tools.

        Args:
            llm: The LLM to use.
            messages: The conversation messages.
            tools: Optional tools list (uses toolset if not provided).

        Returns:
            ChatCompletionResponse on success.
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
    ) -> ChatCompletionResponse:
        """
        Call the LLM with a pre-built request.

        Args:
            llm: The LLM to use.
            request: The chat completion request.

        Returns:
            ChatCompletionResponse on success.
        """
        return llm.completion(request, self.config.model)

    @staticmethod
    def _structured_tool_error(code: str, message: str) -> str:
        return json.dumps(
            {"status": "error", "error": {"code": code, "message": message}},
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _bounded_error(error: Exception, limit: int = 300) -> str:
        message = " ".join(str(error).split())
        return message if len(message) <= limit else f"{message[: limit - 3]}..."

    @staticmethod
    def _validation_error_message(error: Exception) -> str:
        if not isinstance(error, ValidationError):
            return f"Tool arguments failed validation: {ReActAgent._bounded_error(error)}"

        issues = []
        for detail in error.errors(include_input=False, include_url=False)[:3]:
            location = ".".join(str(part) for part in detail.get("loc", ())) or "arguments"
            issues.append(f"{location}: {detail.get('msg', 'invalid value')}")
        return "Invalid tool arguments: " + "; ".join(issues)

    @staticmethod
    def _tool_call_fingerprint(tool_name: str, tool_args: dict) -> str:
        canonical_args = json.dumps(tool_args, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        return f"{tool_name}:{canonical_args}"

    @staticmethod
    def _record_failure_attempt(
        attempts: dict[tuple[str, str], int],
        tool_name: str,
        outcome: ReActToolOutcome,
    ) -> int:
        key = (tool_name, outcome.code or outcome.disposition.value)
        attempts[key] = attempts.get(key, 0) + 1
        return attempts[key]

    @staticmethod
    def _failure_record(tool_name: str, outcome: ReActToolOutcome) -> dict[str, str]:
        return {
            "tool": tool_name,
            "code": outcome.code or outcome.disposition.value,
            "message": outcome.message or "The tool could not complete this part of the request.",
            "disposition": outcome.disposition.value,
        }

    @classmethod
    def _append_failure(
        cls,
        failures: list[dict[str, str]],
        tool_name: str,
        outcome: ReActToolOutcome,
    ) -> None:
        record = cls._failure_record(tool_name, outcome)
        for index, existing in enumerate(failures):
            if existing["tool"] == record["tool"] and existing["code"] == record["code"]:
                failures[index] = record
                return
        failures.append(record)

    @staticmethod
    def _resolve_latest_failure(failures: list[dict[str, str]], tool_name: str) -> None:
        for index in range(len(failures) - 1, -1, -1):
            if failures[index]["tool"] == tool_name:
                del failures[index]
                return

    def _build_policy_response(
        self,
        start_time: int,
        trace: List[ReActStep],
        iterations: int,
        usage: CompletionUsage,
        termination_reason: str,
        verified_results: list[dict[str, str]],
        unresolved_failures: list[dict[str, str]],
    ) -> ChatCompletionResponse:
        lines: list[str] = []
        if verified_results:
            lines.append("Verified results:")
            lines.extend(f"- {item['tool']}: {item['summary']}" for item in verified_results)
        if unresolved_failures:
            if lines:
                lines.append("")
            heading = "Clarification needed:" if termination_reason == "clarification_required" else "Unresolved:"
            lines.append(heading)
            lines.extend(f"- {item['tool']}: {item['message']}" for item in unresolved_failures)
        if not lines:
            lines.append("The tool workflow stopped because it made no further progress.")

        success = bool(verified_results) and not unresolved_failures
        return ChatCompletionResponse(
            id=f"react-{uuid.uuid4().hex[:12]}",
            created=start_time,
            model=str(self.config.model),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content="\n".join(lines)),
                    finish_reason=FinishReason.stop,
                    provider_specific_fields={
                        "react_trace": [step.model_dump() for step in trace],
                        "iterations": iterations,
                        "success": success,
                        "termination_reason": termination_reason,
                        "unresolved_tool_failures": unresolved_failures,
                    },
                )
            ],
            usage=usage if usage.total_tokens > 0 else None,
        )

    def _execute_tool_with_wrappers(
        self,
        ctx: ProcessContext,
        tool_name: str,
        tool_args: dict,
        toolset: ReActToolset,
        thought: Optional[str] = None,
    ) -> tuple[str, list, Optional[ReActToolOutcome]]:
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
            message = f"Unknown tool '{tool_name}'."
            return (
                self._structured_tool_error("unknown_tool", message),
                plugin_messages,
                ReActToolOutcome(
                    disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
                    code="unknown_tool",
                    message=message,
                ),
            )

        # Parse arguments into BaseModel
        try:
            parsed_args = toolspec.parse_args(tool_args)
        except Exception as e:
            message = self._validation_error_message(e)
            return (
                self._structured_tool_error("invalid_arguments", message),
                plugin_messages,
                ReActToolOutcome(
                    disposition=ToolOutcomeDisposition.RETRYABLE_ERROR,
                    code="invalid_arguments",
                    message="Tool arguments failed validation.",
                ),
            )

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
                    tool_output, plugin_messages = self._run_tool_postprocessors(
                        ctx, tool_name, current_args, tool_output, plugin_messages
                    )
                    return (
                        tool_output,
                        plugin_messages,
                        toolset.interpret_result(tool_name, current_args, tool_output),
                    )
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
                message = f"Tool execution failed: {self._bounded_error(e)}"
                tool_output = self._structured_tool_error("execution_error", message)
                tool_output, plugin_messages = self._run_tool_postprocessors(
                    ctx, tool_name, current_args, tool_output, plugin_messages
                )
                return (
                    tool_output,
                    plugin_messages,
                    ReActToolOutcome(
                        disposition=ToolOutcomeDisposition.TERMINAL_ERROR,
                        code="execution_error",
                        message="The tool failed during execution.",
                    ),
                )

        # Run postprocessors
        tool_output, plugin_messages = self._run_tool_postprocessors(
            ctx, tool_name, current_args, tool_output, plugin_messages
        )
        return tool_output, plugin_messages, toolset.interpret_result(tool_name, current_args, tool_output)

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
