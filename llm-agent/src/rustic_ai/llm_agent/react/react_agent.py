import json
import logging
from typing import List, Optional, Union

from pydantic import ConfigDict, Field, field_serializer, field_validator

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    DiscriminatedLLMMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent.llm_agent_conf import Models

from .models import ReActRequest, ReActResponse, ReActStep
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


class ReActAgentConfig(BaseAgentProps):
    """
    Configuration for the ReActAgent.

    This config mirrors relevant fields from LLMAgentConfig while adding
    ReAct-specific settings like max_iterations and toolset.
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


class ReActAgent(Agent[ReActAgentConfig]):
    """
    An agent that implements the ReAct (Reasoning and Acting) pattern.

    The ReActAgent iteratively:
    1. Calls the LLM with the current conversation and available tools
    2. If the LLM requests a tool call, executes the tool and adds the result
    3. Repeats until the LLM provides a final answer or max iterations is reached

    This agent is suitable for simple, self-contained ReAct use cases where
    tools are executed synchronously within the agent. For more complex
    multi-agent scenarios, consider using the message-based approach with
    LLMAgent and separate ToolAgents.
    """

    @processor(clz=ReActRequest, depends_on=["llm"])
    def handle_react_request(self, ctx: ProcessContext[ReActRequest], llm: LLM):
        """
        Process a ReAct request by running the reasoning loop.

        Args:
            ctx: The process context containing the request.
            llm: The LLM dependency for making completion calls.
        """
        request = ctx.payload

        try:
            result = self._run_react_loop(request.query, llm, request.context)
            ctx.send(result)
        except Exception as e:
            logger.error(f"Error in ReAct loop: {e}", exc_info=True)
            ctx.send(
                ReActResponse(
                    answer="An error occurred while processing your request.",
                    success=False,
                    error=str(e),
                )
            )

    def _run_react_loop(
        self,
        query: str,
        llm: LLM,
        context: Optional[dict] = None,
    ) -> ReActResponse:
        """
        Execute the ReAct reasoning loop.

        Args:
            query: The user's query to process.
            llm: The LLM to use for completions.
            context: Optional additional context.

        Returns:
            ReActResponse with the final answer and trace.
        """
        # Build initial messages
        messages: List[DiscriminatedLLMMessage] = [
            SystemMessage(content=self._get_system_prompt()),
            UserMessage(content=self._format_query(query, context)),
        ]

        trace: List[ReActStep] = []
        toolset = self.config.toolset

        for iteration in range(self.config.max_iterations):
            # Call LLM with tools
            response = self._call_llm(llm, messages)

            if isinstance(response, str):
                # Error occurred
                return ReActResponse(
                    answer=response,
                    trace=trace,
                    iterations=iteration + 1,
                    success=False,
                    error=response,
                )

            choice = response.choices[0]
            assistant_message = choice.message

            # Add assistant response to messages
            messages.append(assistant_message)

            # Check if we have tool calls
            if not assistant_message.tool_calls:
                # No tool calls - this is the final answer
                return ReActResponse(
                    answer=assistant_message.content or "",
                    trace=trace,
                    iterations=iteration + 1,
                    success=True,
                )

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

                # Get tool spec and execute
                toolspec = toolset.get_toolspec(tool_name)
                if not toolspec:
                    tool_result = f"Error: Unknown tool '{tool_name}'"
                else:
                    try:
                        parsed_args = toolspec.parse_args(tool_args)
                        tool_result = toolset.execute(tool_name, parsed_args)
                    except Exception as e:
                        logger.warning(f"Error executing tool {tool_name}: {e}")
                        tool_result = f"Error executing tool: {e}"

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

        # Max iterations reached
        return ReActResponse(
            answer="Maximum iterations reached. Unable to complete the task.",
            trace=trace,
            iterations=self.config.max_iterations,
            success=False,
            error="Max iterations reached",
        )

    def _get_system_prompt(self) -> str:
        """Get the system prompt, using custom or default."""
        if self.config.system_prompt:
            return self.config.system_prompt
        return DEFAULT_REACT_SYSTEM_PROMPT

    def _format_query(self, query: str, context: Optional[dict] = None) -> str:
        """Format the user query, optionally including context."""
        if context:
            context_str = json.dumps(context, indent=2)
            return f"Context:\n{context_str}\n\nQuery: {query}"
        return query

    def _call_llm(
        self,
        llm: LLM,
        messages: List[DiscriminatedLLMMessage],
    ) -> Union[ChatCompletionResponse, str]:
        """
        Call the LLM with the given messages and tools.

        Args:
            llm: The LLM to use.
            messages: The conversation messages.

        Returns:
            ChatCompletionResponse on success, error string on failure.
        """
        request = ChatCompletionRequest(
            messages=messages,
            tools=self.config.toolset.chat_tools if self.config.toolset.tool_count > 0 else None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        try:
            response = llm.completion(request, self.config.model)
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return f"LLM call failed: {e}"
