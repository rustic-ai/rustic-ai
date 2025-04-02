import json
from typing import Union


class JExpr:
    def __init__(self, expression=""):
        self.expression = expression

    # Field Access
    def __getattr__(self, name):
        return JExpr(f"{self.expression}.{name}" if self.expression else name)

    # Function Calls
    def __call__(self, *args):
        def serialize_arg(arg):
            if isinstance(arg, JExpr):
                return arg.serialize()
            elif isinstance(arg, str):
                return json.dumps(arg)  # Properly quote strings
            elif isinstance(arg, dict):
                return JObj(arg).serialize()
            elif isinstance(arg, list):
                return JArray(arg).serialize()
            else:
                return json.dumps(arg)  # Handles numbers, booleans, etc.

        args_str = ", ".join(serialize_arg(arg) for arg in args)
        return JExpr(f"{self.expression}({args_str})")

    # Filters
    def filter(self, condition):
        condition_expr = condition.serialize() if isinstance(condition, JExpr) else str(condition)
        return JExpr(f"{self.expression}[{condition_expr}]")

    def order_by(self, *keys):
        keys_expr = ", ".join(k.serialize() if isinstance(k, JExpr) else str(k) for k in keys)
        return JExpr(f"{self.expression}^({keys_expr})")

    def wildcard(self):
        return JExpr(f"{self.expression}.*")

    def descendants(self):
        return JExpr(f"{self.expression}.**")

    # Comparison Operators
    def __eq__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} = {other_expr}")

    def __ne__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} != {other_expr}")

    def __gt__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} > {other_expr}")

    def __lt__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} < {other_expr}")

    def __ge__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} >= {other_expr}")

    def __le__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"{self.expression} <= {other_expr}")

    # Array Indexing
    def __getitem__(self, key):
        if isinstance(key, int):
            return JExpr(f"{self.expression}[{key}]")
        elif isinstance(key, slice):
            start = key.start if key.start is not None else ""
            # Adjust the stop index for JSONata's inclusive ranges
            stop = key.stop - 1 if key.stop is not None else ""
            return JExpr(f"{self.expression}[{start}..{stop}]")
        elif isinstance(key, str):
            key_expr = json.dumps(key)
            return JExpr(f"{self.expression}[{key_expr}]")
        elif isinstance(key, JExpr):
            return JExpr(f"{self.expression}[{key.serialize()}]")
        else:
            raise TypeError("Invalid key type for JSONata expression")

    # String Representation
    def __str__(self):
        return self.expression

    def __repr__(self):
        return f"JExpr({self.expression})"

    # Concatenation Operator
    def __and__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} & {other_expr})")

    def __add__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} + {other_expr})")

    def __sub__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} - {other_expr})")

    def __mul__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} * {other_expr})")

    def __truediv__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} / {other_expr})")

    def __mod__(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} % {other_expr})")

    def __neg__(self):
        return JExpr(f"-{self.expression}")

    def in_(self, array_expr):
        aexpr = array_expr
        if not isinstance(array_expr, JExpr) and isinstance(array_expr, list):
            aexpr = JArray(array_expr)
        elif not isinstance(array_expr, JExpr):
            aexpr = JExpr(json.dumps(array_expr))

        array_str = aexpr.serialize()

        return JExpr(f"({self.expression} in {array_str})")

    def and_(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} and {other_expr})")

    def or_(self, other):
        other_expr = other.serialize() if isinstance(other, JExpr) else json.dumps(other)
        return JExpr(f"({self.expression} or {other_expr})")

    @staticmethod
    def range(start, end):
        start_expr = start.serialize() if isinstance(start, JExpr) else json.dumps(start)
        end_expr = end.serialize() if isinstance(end, JExpr) else json.dumps(end)
        return JExpr(f"[{start_expr}..{end_expr}]")

    # Serialize Single Expression
    def serialize(self):
        return self.expression

    # Recursive Serialization for Nested Structures
    @staticmethod
    def serialize_expr(structure):
        if isinstance(structure, JExpr):
            return json.loads(f'"{structure.serialize()}"')
        elif isinstance(structure, dict):
            return {k: JExpr.serialize_expr(v) for k, v in structure.items()}
        elif isinstance(structure, list):
            return [JExpr.serialize_expr(v) for v in structure]
        else:
            return structure


class JStr(JExpr):
    def __init__(self, value: str):
        if not isinstance(value, str):
            raise TypeError("JString expects a Python string")
        # Properly quote and escape the string for JSONata
        expression = json.dumps(value)
        super().__init__(expression)


class JNum(JExpr):
    def __init__(self, value):
        # Accept int or float
        if not isinstance(value, (int, float)):
            raise TypeError("JNumber expects an int or float")
        # Convert to string without additional quotes
        expression = str(value)
        super().__init__(expression)


class JBool(JExpr):
    def __init__(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("JBoolean expects a Python boolean")
        # Convert True/False to lowercase true/false for JSONata
        expression = "true" if value else "false"
        super().__init__(expression)


class JFn:
    def __init__(self, params, body_expr):
        self.params = params  # List of parameter names, should include `$` prefix
        self.body_expr = body_expr  # JExpr instance representing the function body

    def serialize(self):
        params_str = ", ".join(self.params)
        body_str = self.body_expr.serialize()
        return f"function({params_str}){{ {body_str} }}"


class JNull(JExpr):
    def __init__(self):
        super().__init__("null")


class JArray(JExpr):
    def __init__(self, values):
        if not isinstance(values, list):
            raise TypeError("JArray expects a Python list")
        converted_values = [_to_jexpr(v) for v in values]
        expression = "[" + ", ".join(v.serialize() for v in converted_values) + "]"
        super().__init__(expression)


class JRegex(JExpr):
    def __init__(self, pattern, flags=""):
        if not isinstance(pattern, str):
            raise TypeError("JRegex expects a Python string pattern")
        if not isinstance(flags, str):
            raise TypeError("JRegex expects a Python string flags")
        expression = f"/{pattern}/{flags}"
        super().__init__(expression)

    def __str__(self):
        return self.expression


class JAssignmernt(JExpr):
    def __init__(self, var_expr: Union[JExpr, str], value: str):
        self.var: JExpr = var_expr if isinstance(var_expr, JExpr) else JExpr(var_expr)
        if not self.var.expression.startswith("$"):
            self.var = JExpr(f"${self.var.expression}")

        self.value = value

        expression = f"{self.var.expression} := {value}"
        super().__init__(expression)


def _to_jexpr(value):
    if isinstance(value, JExpr):
        return value
    if isinstance(value, JFn):
        return value
    if value is None:
        return JNull()
    if isinstance(value, bool):
        return JBool(value)
    if isinstance(value, (int, float)):
        return JNum(value)
    if isinstance(value, str):
        if value.startswith("$"):
            return JExpr(value)
        return JStr(value)
    if isinstance(value, list):
        return JArray(value)
    if isinstance(value, dict):
        return JObj(value)
    raise TypeError(f"Cannot convert value of type {type(value).__name__} to JExpr")


class JObj(JExpr):
    def __init__(self, obj):
        if not isinstance(obj, dict):
            raise TypeError("JObject expects a Python dict")
        items = []
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("JObject keys must be strings")
            vexpr = _to_jexpr(value)
            key_str = json.dumps(key)
            items.append(f"{key_str}: {vexpr.serialize()}")
        expression = "{" + ", ".join(items) + "}"
        super().__init__(expression)


class JxScript:
    """
    Represents a collection of JSONata expressions (JExpr objects or strings)
    that can be combined into a single JSONata script.
    """

    def __init__(self, *expressions):
        # expressions is a tuple of JExpr or strings representing JSONata code.
        # Storing them in a list allows for easy modification (e.g., append).
        if not all(isinstance(expr, (JFn, JExpr, str, JxScript)) for expr in expressions):
            raise TypeError("JxScript expects JFn, JxScript, JExpr or str expressions")
        self.expressions = list(expressions)

    def append(self, expr):
        # Append a new expression (JExpr or string).
        # Returns self to allow method chaining: script.append(...).append(...)
        if not isinstance(expr, (JFn, JExpr, str, JxScript)):
            raise TypeError("JxScript expects JFn, JxScript, JExpr or str expressions")
        self.expressions.append(expr)
        return self

    def serialize(self):
        # Converts each expression to its JSONata string form.
        # - If expr is a JExpr (or similar class) with a serialize() method, use that.
        # - Otherwise, default to str(expr).
        serialized_parts = []
        for expr in self.expressions:
            if hasattr(expr, "serialize") and callable(expr.serialize):
                serialized_parts.append(expr.serialize())
            else:
                serialized_parts.append(str(expr))

        # Joins expressions with semicolons and wraps everything in parentheses.
        # Example: (expr1; expr2; expr3)
        return "(" + "; ".join(serialized_parts) + ")"

    def __str__(self):
        # Returns the serialized script as a string.
        return self.serialize()

    def __repr__(self):
        # Provides a developer-friendly representation.
        return f"JxScript({self.expressions})"
