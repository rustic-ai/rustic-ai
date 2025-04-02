import pytest

import rustic_ai.core.utils.jx as jx
from rustic_ai.core.utils.jexpr import JExpr, JFn, JNull, JObj, JxScript


# Helper function to serialize JxScript
def serialize_jxscript(script):
    return script.serialize()


class TestJxScript:
    def test_empty_script(self):
        """Test that an empty JxScript serializes correctly."""
        script = JxScript()
        expected = "()"
        assert serialize_jxscript(script) == expected, "Empty script should serialize to ()"

    def test_single_jexpr(self):
        """Test a JxScript with a single JExpr."""
        expr = JExpr("payload.numkey > 10")
        script = JxScript(expr)
        expected = "(payload.numkey > 10)"
        assert serialize_jxscript(script) == expected, "Single JExpr serialization failed"

    def test_single_string_expression(self):
        """Test a JxScript with a single raw string expression."""
        expr = "$sum(payload.values)"
        script = JxScript(expr)
        expected = "($sum(payload.values))"
        assert serialize_jxscript(script) == expected, "Single string expression serialization failed"

    def test_multiple_jexprs(self):
        """Test a JxScript with multiple JExpr objects."""
        expr1 = jx.assign("$x", 10)
        expr2 = jx.assign("$y", 20)
        conditional = jx.ternary(JExpr("$x") > JExpr("$y"), "x is greater", "y is greater")
        script = JxScript(expr1, expr2, conditional)
        expected = '($x := 10; $y := 20; ($x > $y) ? "x is greater" : "y is greater")'
        assert serialize_jxscript(script) == expected, "Multiple JExprs serialization failed"

    def test_append_method(self):
        """Test the append method of JxScript."""
        script = JxScript()
        script.append(jx.assign("$a", 5))
        script.append(jx.assign("$b", 15))
        conditional = jx.ternary(JExpr("$a") + JExpr("$b") > 20, "High", "Low")
        script.append(conditional)
        expected = '($a := 5; $b := 15; (($a + $b) > 20) ? "High" : "Low")'
        assert serialize_jxscript(script) == expected, "Append method serialization failed"

    def test_mixed_expressions(self):
        """Test a JxScript with mixed JExpr objects and raw strings."""
        expr1 = jx.assign("$name", "John Doe")
        expr2 = '$greeting := "Hello, " & $name'
        expr3 = JExpr('$greeting & "!"')
        script = JxScript(expr1, expr2, expr3)
        expected = '($name := "John Doe"; $greeting := "Hello, " & $name; $greeting & "!")'
        assert serialize_jxscript(script) == expected, "Mixed expressions serialization failed"

    def test_nested_jxscript(self):
        """Test nesting JxScript instances within a JxScript."""
        inner_script = JxScript(
            jx.assign("$innerVar", 100),
            jx.ternary(JExpr("$innerVar") > 50, "Large", "Small"),
        )
        outer_script = JxScript(
            jx.assign("$outerVar", 200),
            inner_script,
            jx.ternary(JExpr("$outerVar") > 150, "$innerVar", "$outerVar"),
        )
        expected = '($outerVar := 200; ($innerVar := 100; ($innerVar > 50) ? "Large" : "Small"); ($outerVar > 150) ? $innerVar : $outerVar)'
        assert serialize_jxscript(outer_script) == expected, "Nested JxScript serialization failed"

    def test_invalid_expression_append(self):
        """Test that appending an invalid expression raises an error."""
        script = JxScript()
        with pytest.raises(TypeError):
            # Assuming JxScript should only accept JExpr or str
            script.append(5)  # Invalid type

    def test_complex_script(self):
        """Test a complex script with function definitions and conditionals."""
        one_form_assignment = jx.assign(
            "$OneForm",
            JFn(
                [],
                JObj(
                    {
                        "topics": "topic_one",
                        "format": "ONE_FORM",
                        "payload": {
                            "key_one": JExpr("payload.key"),
                            "origin_id": JExpr("$.origin.id"),
                        },
                    }
                ),
            ),
        )

        two_form_assignment = jx.assign(
            "$TwoForm",
            JFn(
                [],
                JObj(
                    {
                        "topics": ["topic_two"],
                        "format": "TWO_FORM",
                        "payload": {
                            "key_two": JExpr("payload.key"),
                            "origin_id": JExpr("$.origin.id"),
                        },
                    }
                ),
            ),
        )

        conditional_expr = jx.ternary(JExpr("payload.numkey") > 10, JExpr("$OneForm()"), JExpr("$TwoForm()"))

        script = JxScript(one_form_assignment, two_form_assignment, conditional_expr)

        expected_stmts = [
            '$OneForm := function(){ {"topics": "topic_one", "format": "ONE_FORM", "payload": {"key_one": payload.key, "origin_id": $.origin.id}} }',
            '$TwoForm := function(){ {"topics": ["topic_two"], "format": "TWO_FORM", "payload": {"key_two": payload.key, "origin_id": $.origin.id}} }',
            "(payload.numkey > 10) ? $OneForm() : $TwoForm()",
        ]

        joint = "; ".join(expected_stmts)
        expected = f"""({joint})"""

        serialized = serialize_jxscript(script)
        assert serialized == expected, "Complex script serialization failed"

    def test_parentheses_handling(self):
        """Ensure that the script is properly wrapped in parentheses."""
        expr1 = jx.assign("$a", 1)
        expr2 = jx.assign("$b", 2)
        script = JxScript(expr1, expr2)
        serialized = serialize_jxscript(script)
        assert serialized.startswith("(") and serialized.endswith(")"), "Script should be wrapped in parentheses"

    def test_str_method(self):
        """Test the __str__ method of JxScript."""
        expr1 = jx.assign("$a", 1)
        expr2 = jx.assign("$b", 2)
        script = JxScript(expr1, expr2)
        expected_str = "($a := 1; $b := 2)"
        assert str(script) == expected_str, "__str__ method does not match expected output"

    def test_chaining_append(self):
        """Test that append can be chained."""
        script = JxScript()
        script.append(jx.assign("$a", 1)).append(jx.assign("$b", 2))
        expected = "($a := 1; $b := 2)"
        assert serialize_jxscript(script) == expected, "Chained append failed"

    def test_expression_order(self):
        """Test that expressions are serialized in the order they were added."""
        expr1 = jx.assign("$first", "first")
        expr2 = jx.assign("$second", "second")
        script = JxScript(expr1, expr2)
        expected = '($first := "first"; $second := "second")'
        assert serialize_jxscript(script) == expected, "Expression order incorrect"

    def test_append_jxscript(self):
        """Test appending another JxScript instance."""
        inner_script = JxScript(jx.assign("$inner", 100), jx.ternary(JExpr("$inner") > 50, "High", "Low"))
        outer_script = JxScript(jx.assign("$outer", 200))
        outer_script.append(inner_script)
        expected = '($outer := 200; ($inner := 100; ($inner > 50) ? "High" : "Low"))'
        assert serialize_jxscript(outer_script) == expected, "Appending JxScript instance failed"

    def test_complex_nested_scripts(self):
        """Test deeply nested JxScript instances."""
        level3 = JxScript(
            jx.assign("$level3Var", 300),
            jx.ternary(JExpr("$level3Var") > 250, "Level3 High", "Level3 Low"),
        )
        level2 = JxScript(jx.assign("$level2Var", 200), level3)
        level1 = JxScript(jx.assign("$level1Var", 100), level2)
        expected = '($level1Var := 100; ($level2Var := 200; ($level3Var := 300; ($level3Var > 250) ? "Level3 High" : "Level3 Low")))'
        assert serialize_jxscript(level1) == expected, "Deeply nested JxScript serialization failed"

    def test_invalid_expression_in_constructor(self):
        """Test that initializing JxScript with invalid expressions raises an error."""
        with pytest.raises(TypeError):
            # Assuming JxScript should only accept JExpr or str
            JxScript(123)  # Invalid type

    def test_script_with_null_expression(self):
        """Test that JxScript can handle expressions that serialize to null."""
        expr1 = jx.assign("$a", JNull())
        expr2 = jx.assign("$b", "Test")
        script = JxScript(expr1, expr2)
        expected = '($a := null; $b := "Test")'
        assert serialize_jxscript(script) == expected, "Script with null expression failed"

    def test_script_with_functions(self):
        """Test that JxScript can handle function expressions."""
        func_assign = jx.assign("$add", JFn(["$x", "$y"], JExpr("$x") + JExpr("$y")))
        call_func = JExpr("$add(5, 10)")
        script = JxScript(func_assign, call_func)
        expected = "($add := function($x, $y){ ($x + $y) }; $add(5, 10))"
        assert serialize_jxscript(script) == expected, "Script with function expressions failed"

    def test_script_with_array_indexing(self):
        """Test that JxScript can handle array indexing expressions."""
        expr1 = jx.assign("$array", [10, 20, 30, 40, 50])
        expr2 = JExpr("$array[2]")
        script = JxScript(expr1, expr2)
        expected = "($array := [10, 20, 30, 40, 50]; $array[2])"
        assert serialize_jxscript(script) == expected, "Script with array indexing failed"

    def test_script_with_object_field_access(self):
        """Test that JxScript can handle object field access."""
        expr1 = jx.assign("$obj", {"foo": {"bar": "baz"}})
        expr2 = JExpr("$obj.foo.bar")
        script = JxScript(expr1, expr2)
        expected = '($obj := {"foo": {"bar": "baz"}}; $obj.foo.bar)'
        assert serialize_jxscript(script) == expected, "Script with object field access failed"

    def test_script_with_conditional_logic(self):
        """Test that JxScript can handle complex conditional logic."""
        expr1 = jx.assign("$age", 25)
        expr2 = jx.assign("$status", "unknown")
        conditional = jx.ternary(JExpr("$age") >= 18, "adult", "minor")
        script = JxScript(expr1, expr2, conditional)
        expected = '($age := 25; $status := "unknown"; ($age >= 18) ? "adult" : "minor")'
        assert serialize_jxscript(script) == expected, "Script with conditional logic failed"

    def test_script_with_multiple_assignments(self):
        """Test that JxScript can handle multiple assignments."""
        expr1 = jx.assign("$a", 1)
        expr2 = jx.assign("$b", 2)
        expr3 = jx.assign("$c", 3)
        script = JxScript(expr1, expr2, expr3)
        expected = "($a := 1; $b := 2; $c := 3)"
        assert serialize_jxscript(script) == expected, "Script with multiple assignments failed"

    def test_script_with_math_operations(self):
        """Test that JxScript can handle mathematical operations."""
        expr1 = jx.assign("$x", 10)
        expr2 = jx.assign("$y", 5)
        expr3 = JExpr("$x * $y + ($x / $y) - ($x % $y)")
        script = JxScript(expr1, expr2, expr3)
        expected = "($x := 10; $y := 5; $x * $y + ($x / $y) - ($x % $y))"
        assert serialize_jxscript(script) == expected, "Script with math operations failed"

    def test_script_with_boolean_logic(self):
        """Test that JxScript can handle boolean logic."""
        expr1 = jx.assign("$isActive", True)
        expr2 = jx.assign("$hasAccess", False)
        expr3 = JExpr("$isActive and $hasAccess")
        script = JxScript(expr1, expr2, expr3)
        expected = "($isActive := true; $hasAccess := false; $isActive and $hasAccess)"
        assert serialize_jxscript(script) == expected, "Script with boolean logic failed"

    def test_script_with_nested_objects(self):
        """Test that JxScript can handle nested objects."""
        expr1 = jx.assign(
            "$user",
            {
                "name": "Alice",
                "details": {
                    "age": 30,
                    "address": {"city": "Wonderland", "zip": "12345"},
                },
            },
        )
        expr2 = JExpr("$user.details.address.city")
        script = JxScript(expr1, expr2)
        expected = '($user := {"name": "Alice", "details": {"age": 30, "address": {"city": "Wonderland", "zip": "12345"}}}; $user.details.address.city)'
        assert serialize_jxscript(script) == expected, "Script with nested objects failed"

    def test_script_with_arrays_and_objects(self):
        """Test that JxScript can handle arrays containing objects."""
        expr1 = jx.assign(
            "$items",
            [{"id": 1, "value": "A"}, {"id": 2, "value": "B"}, {"id": 3, "value": "C"}],
        )
        expr2 = JExpr("$items[1].value")
        script = JxScript(expr1, expr2)
        expected = (
            '($items := [{"id": 1, "value": "A"}, {"id": 2, "value": "B"}, {"id": 3, "value": "C"}]; $items[1].value)'
        )
        assert serialize_jxscript(script) == expected, "Script with arrays and objects failed"

    def test_script_with_functions_and_calls(self):
        """Test that JxScript can handle function definitions and calls."""
        func_assign = jx.assign("$multiply", JFn(["$a", "$b"], JExpr("$a") * JExpr("$b")))
        func_call = JExpr("$multiply(3, 4)")
        script = JxScript(func_assign, func_call)
        expected = "($multiply := function($a, $b){ ($a * $b) }; $multiply(3, 4))"
        assert serialize_jxscript(script) == expected, "Script with functions and calls failed"

    def test_script_with_error_handling(self):
        """Test that JxScript handles expressions that might cause errors gracefully."""
        # For example, accessing a non-existent field
        expr1 = jx.assign("$obj", {"foo": "bar"})
        expr2 = JExpr("$obj.nonExistent")
        script = JxScript(expr1, expr2)
        expected = '($obj := {"foo": "bar"}; $obj.nonExistent)'
        assert serialize_jxscript(script) == expected, "Script with potential errors serialization failed"

    def test_script_with_null_handling(self):
        """Test that JxScript can handle null values."""
        expr1 = jx.assign("$data", None)
        expr2 = jx.ternary(JExpr("$data") == JNull(), "No Data", "Data Exists")
        script = JxScript(expr1, expr2)
        expected = '($data := null; (null = $data) ? "No Data" : "Data Exists")'
        assert serialize_jxscript(script) == expected, "Script with null handling failed"

    def test_script_with_null_expression1(self):
        """Test that JxScript can include expressions that are explicitly null."""
        expr1 = jx.assign("$value", JNull())
        expr2 = JExpr("$value")
        script = JxScript(expr1, expr2)
        expected = "($value := null; $value)"
        assert serialize_jxscript(script) == expected, "Script with null expressions failed"

    def test_script_with_array_operations(self):
        """Test that JxScript can handle array operations."""
        expr1 = jx.assign("$numbers", [1, 2, 3, 4, 5])
        expr2 = jx.sum("$numbers")
        script = JxScript(expr1, expr2)
        expected = "($numbers := [1, 2, 3, 4, 5]; $sum($numbers))"
        assert serialize_jxscript(script) == expected, "Script with array operations failed"

    def test_script_with_lambda_functions(self):
        """Test that JxScript can handle lambda functions within expressions."""
        map_expr = jx.map([1, 2, 3], lambda x: JExpr("$x * 2"))
        script = JxScript(map_expr)
        expected = "($map([1, 2, 3], function($x){ $x * 2 }))"
        assert serialize_jxscript(script) == expected, "Script with lambda functions failed"

    def test_script_with_multiple_lambdas(self):
        """Test that JxScript can handle multiple lambda functions."""
        map_expr = jx.map([1, 2, 3], lambda x: x * 2)
        filter_expr = jx.filter([1, 2, 3, 4], lambda x: JExpr("$x > 2"))
        script = JxScript(map_expr, filter_expr)
        expected = "($map([1, 2, 3], function($x){ ($x * 2) }); " "$filter([1, 2, 3, 4], function($x){ $x > 2 }))"
        assert serialize_jxscript(script) == expected, "Script with multiple lambda functions failed"

    def test_script_with_complex_objects_and_arrays(self):
        """Test that JxScript can handle complex nested structures."""
        expr1 = jx.assign(
            "$data",
            {
                "users": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                    {"id": 3, "name": "Charlie"},
                ],
                "settings": {"theme": "dark", "notifications": True},
            },
        )
        expr2 = JExpr("$data.users[1].name")
        script = JxScript(expr1, expr2)
        expected = (
            '($data := {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Charlie"}],'
            ' "settings": {"theme": "dark", "notifications": true}}; $data.users[1].name)',
        )
        assert serialize_jxscript(script) == expected[0], "Script with complex objects and arrays failed"

    def test_script_with_function_returning_object(self):
        """Test that JxScript can handle functions returning objects."""
        func_assign = jx.assign("$createUser", JFn(["$id", "$name"], JObj({"id": "$id", "name": "$name"})))
        func_call = JExpr('$createUser(1, "Alice")')
        script = JxScript(func_assign, func_call)
        expected = '($createUser := function($id, $name){ {"id": $id, "name": $name} }; $createUser(1, "Alice"))'
        assert serialize_jxscript(script) == expected, "Script with function returning object failed"

    def test_script_with_if_else(self):
        """Test that JxScript can handle if-else conditional expressions."""
        expr1 = jx.assign("$score", 85)
        expr2 = jx.ternary(JExpr("$score") >= 90, "A", jx.ternary(JExpr("$score") >= 80, "B", "C"))
        script = JxScript(expr1, expr2)
        expected = '($score := 85; ($score >= 90) ? "A" : ($score >= 80) ? "B" : "C")'
        assert serialize_jxscript(script) == expected, "Script with nested ternary expressions failed"

    def test_script_with_nested_objects_and_functions(self):
        """Test that JxScript can handle nested objects and functions."""
        func_assign = jx.assign(
            "$getUser",
            JFn(["$id"], JObj({"id": "$id", "name": JExpr("User") & JExpr("$id")})),
        )
        expr1 = jx.assign("$user1", JExpr("$getUser(1)"))
        expr2 = jx.assign("$user2", JExpr("$getUser(2)"))
        script = JxScript(func_assign, expr1, expr2)
        expected = (
            '($getUser := function($id){ {"id": $id, "name": (User & $id)} }; '
            "$user1 := $getUser(1); "
            "$user2 := $getUser(2))"
        )
        assert serialize_jxscript(script) == expected, "Script with nested objects and functions failed"
