import pytest

from rustic_ai.core.utils.cel_expr import CelExpressionEvaluator


class TestCelExpressionEvaluator:
    def setup_method(self):
        self.evaluator = CelExpressionEvaluator()

    def test_simple_expression(self):
        expr = "payload.numkey > 10"
        result = self.evaluator.eval(expr, {"payload": {"numkey": 15}})
        assert result is True, "Expression should evaluate to True"

    def test_simple_false_expression(self):
        expr = "payload.numkey > 10"
        result = self.evaluator.eval(expr, {"payload": {"numkey": 5}})
        assert result is False, "Expression should evaluate to False"

    def test_string_comparison(self):
        expr = "payload.name == 'Alice'"
        result = self.evaluator.eval(expr, {"payload": {"name": "Alice"}})
        assert result is True

    def test_arithmetic_expression(self):
        expr = "payload.x * payload.y + 10"
        result = self.evaluator.eval(expr, {"payload": {"x": 2, "y": 5}})
        assert result == 20

    def test_array_access(self):
        expr = "payload.values[1]"
        result = self.evaluator.eval(expr, {"payload": {"values": [10, 20, 30]}})
        assert result == 20

    def test_object_field_access(self):
        expr = "payload.user.name"
        result = self.evaluator.eval(expr, {"payload": {"user": {"name": "Bob"}}})
        assert result == "Bob"

    def test_conditional_expression(self):
        expr = "payload.age > 18 ? 'adult' : 'minor'"
        result = self.evaluator.eval(expr, {"payload": {"age": 20}})
        assert result == "adult"

    def test_nested_objects_and_arrays(self):
        expr = "payload.users[0].details.city"
        result = self.evaluator.eval(
            expr,
            {
                "payload": {
                    "users": [
                        {"details": {"city": "Wonderland"}},
                        {"details": {"city": "Elsewhere"}},
                    ]
                }
            },
        )
        assert result == "Wonderland"

    def test_boolean_logic(self):
        expr = "payload.isActive && !payload.isBanned"
        result = self.evaluator.eval(expr, {"payload": {"isActive": True, "isBanned": False}})
        assert result is True

    def test_math_operations(self):
        expr = "(payload.a + payload.b) * payload.c"
        result = self.evaluator.eval(expr, {"payload": {"a": 2.0, "b": 3.0, "c": 4.0}})
        assert result == 20.0

    def test_null_check(self):
        expr = "payload.value == null"
        result = self.evaluator.eval(expr, {"payload": {"value": None}})
        assert result is True

    def test_custom_function_uppercase(self):
        def caps(x):
            return x.upper()

        self.evaluator.add_function("caps", caps)
        expr = "caps(payload.name)"
        result = self.evaluator.eval(expr, {"payload": {"name": "rustic"}})
        assert result == "RUSTIC"

    def test_multiple_custom_functions(self):
        def add(a, b):
            return a + b

        def square(x):
            return x * x

        self.evaluator.add_function("add", add)
        self.evaluator.add_function("square", square)

        expr = "square(add(payload.a, payload.b))"
        result = self.evaluator.eval(expr, {"payload": {"a": 2, "b": 3}})
        assert result == 25

    def test_expression_with_error(self):
        expr = "payload.nonexistent.field"
        with pytest.raises(Exception):
            self.evaluator.eval(expr, {"payload": {"exists": "yes"}})

    def test_expression_with_complex_data(self):
        expr = "payload.orders[0].items[1].quantity"
        result = self.evaluator.eval(
            expr,
            {"payload": {"orders": [{"items": [{"id": "item-1", "quantity": 2}, {"id": "item-2", "quantity": 5}]}]}},
        )
        assert result == 5
