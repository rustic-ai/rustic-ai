from typing import Any, Dict, Optional

from pydantic import BaseModel


class ReActStep(BaseModel):
    """
    Single step in the ReAct reasoning trace.

    This model is used to record each thought-action-observation cycle
    in the ReAct loop. The trace is stored in the ChatCompletionResponse's
    Choice.provider_specific_fields["react_trace"] as a list of ReActStep dicts.
    """

    thought: Optional[str] = None
    """The reasoning/thought from the LLM before taking action."""

    action: str
    """The name of the tool that was called."""

    action_input: Dict[str, Any]
    """The input arguments passed to the tool."""

    observation: str
    """The result returned from the tool execution."""
