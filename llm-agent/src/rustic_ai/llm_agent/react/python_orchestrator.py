import traceback
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful.models import (
    CodeSnippet,
)
from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful.python_exec_executor import (
    PythonExecExecutor,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset


class PythonOrchestratorParams(BaseModel):
    """Parameters for the Python Orchestrator tool."""

    code: str = Field(description="The Python code to execute.")


class PythonOrchestratorToolset(ReActToolset):
    """
    A toolset that exposes a tool for executing Python code which can orchestrate other tools.

    This enables specific "Programmatic Tool Calling" patterns where the LLM writes a Python
    script to call other tools in a loop, filter data, etc., entirely within one "turn"
    of the main agent loop.

    WARNING: This executes arbitrary code provided by the LLM. Use with caution and
    only in sandboxed environments (Docker, etc.) in production.
    """

    inner_toolset: ReActToolset = Field(
        description="The toolset containing tools that can be called from within the Python code."
    )
    tool_name: str = Field(
        default="python_orchestrator", description="Name of the tool exposed to the LLM."
    )
    allowed_modules: List[str] = Field(
        default_factory=lambda: ["json", "math", "datetime", "re", "random"],
        description="List of modules allowed to be imported in the executed code.",
    )

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return the tool specification for the orchestrator."""
        tool_docs = self._generate_tool_documentation()
        description = (
            "Executes Python code. You can use this to chain multiple tool calls, "
            "process data, or perform calculations. "
            "To call other tools, simply invoke them as functions with their arguments.\n\n"
            f"AVAILABLE FUNCTIONS:\n{tool_docs}\n\n"
            "Example:\n"
            "```python\n"
            "# Call a tool and capture output\n"
            f"data = {self.inner_toolset.tool_names[0] if self.inner_toolset.tool_count > 0 else 'tool_name'}(arg='value')\n"
            "print(data)\n"
            "```"
        )
        return [
            ToolSpec(
                name=self.tool_name,
                description=description,
                parameter_class=PythonOrchestratorParams,
            )
        ]

    def _generate_tool_documentation(self) -> str:
        """Generate documentation for inner tools to include in the prompt."""
        docs = []
        for spec in self.inner_toolset.get_toolspecs():
            # Get schema properties
            schema = spec.parameter_class.model_json_schema()
            props = schema.get("properties", {})
            required = schema.get("required", [])

            # Format arguments signature
            args_list = []
            for prop_name, prop_info in props.items():
                arg_desc = prop_name
                # Add type info if available?
                if prop_name not in required:
                    arg_desc += "=None"
                args_list.append(arg_desc)

            signature = f"{spec.name}({', '.join(args_list)})"
            docs.append(f"- {signature}: {spec.description}")
        return "\n".join(docs)

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """Execute the Python code."""
        if tool_name != self.tool_name:
            raise ValueError(f"Unknown tool: {tool_name}")

        if not isinstance(args, PythonOrchestratorParams):
            raise TypeError(
                f"Expected args to be PythonOrchestratorParams, got {type(args).__name__}"
            )

        code = args.code
        return self._execute_code(code)

    def _execute_code(self, code: str) -> str:
        """
        Execute the provided Python code using the PythonExecExecutor for localized sandboxing.
        """
        # Create function wrappers for all tools in the inner toolset
        tool_bindings = self._create_tool_bindings()

        # Initialize the executor with allowed modules
        executor = PythonExecExecutor(
            whitelisted_imports=set(self.allowed_modules)
        )

        # Inject the tool functions into the executor's scope
        # PythonExecExecutor maintains _local_vars internally for the execution context
        executor._local_vars.update(tool_bindings)

        try:
            # Execute the code snippet via the sandboxed PythonExecExecutor.
            # Additional validation (e.g., AST-based checks) can be added here if needed.
            snippet = CodeSnippet(language="python", code=code)
            result = executor.run(snippet)

            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(f"Errors:\n{result.stderr}")
            if result.exception:
                output.append(f"Exception: {result.exception.type}: {result.exception.message}")

            final_output = "\n".join(output)
            return final_output if final_output.strip() else "Code executed successfully (no output)."

        except Exception:
            # Return the traceback as the tool output so the LLM can debug
            return f"Error executing code:\n{traceback.format_exc()}"

    def _create_tool_bindings(self) -> Dict[str, Any]:
        """Create function wrappers for all tools in the inner toolset."""
        bindings = {}

        for spec in self.inner_toolset.get_toolspecs():
            # Create a closure for the tool execution
            # We need to handle argument parsing here because the python code calls it like a function
            # func(arg1=val1, arg2=val2) -> ReActToolset.execute -> "output"
            def make_tool_func(tool_name: str, tool_spec: ToolSpec):
                def tool_wrapper(**kwargs):
                    # Validate args against the Pydantic model
                    try:
                        # Construct the parameter model from kwargs
                        # This assumes kwargs match the fields of the parameter_class
                        params = tool_spec.parameter_class(**kwargs)
                        return self.inner_toolset.execute(tool_name, params)
                    except Exception as e:
                        return f"Error calling tool '{tool_name}': {e}"

                return tool_wrapper

            # Bind to the tool name (e.g., 'get_weather')
            bindings[spec.name] = make_tool_func(spec.name, spec)

        return bindings
