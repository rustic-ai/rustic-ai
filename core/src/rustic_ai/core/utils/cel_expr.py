from typing import Any, Callable, Dict, Optional

import celpy


class CelExpressionEvaluator:
    """
    Unified CEL expression evaluator for Rustic AI.
    Wraps cel-python to provide an easy API for evaluating expressions with context.
    """

    def __init__(self):
        self.celpy_env = celpy.Environment()
        self._custom_funcs: Dict[str, Callable] = {}

    def add_function(self, name: str, func: Callable):
        """
        Add a custom function to the CEL environment.
        """
        self._custom_funcs[name] = func

    def _build_context(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert plain Python values into CEL types for evaluation.
        """
        ctx = {}
        for key, value in variables.items():
            if isinstance(value, dict) or isinstance(value, list):
                ctx[key] = celpy.json_to_cel(value)
            else:
                ctx[key] = value

        return ctx

    def compile(self, expression: str):
        """
        Compile CEL expression into a reusable program.
        Uses caching for performance.
        """
        ast = self.celpy_env.compile(expression)
        prgm = self.celpy_env.program(ast, functions=self._custom_funcs)

        return prgm

    def eval(self, expression: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        """
        Evaluate a CEL expression with optional variables.
        """
        prgm = self.compile(expression)
        ctx = self._build_context(variables or {})

        return prgm.evaluate(ctx)
