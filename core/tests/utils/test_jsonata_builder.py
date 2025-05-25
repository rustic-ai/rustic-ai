from datetime import datetime, timezone
import json
from typing import Dict

from dateutil import parser
from jsonata import Jsonata
import pytest

from rustic_ai.core.utils import jx
from rustic_ai.core.utils.jexpr import JArray, JExpr, JFn, JNum, JObj, JStr, JxScript


# Helper function to execute JExpr expressions
def execute_jexpr(expression_string: str, data: dict):
    expr = Jsonata(expression_string)
    result = expr.evaluate(data)
    return result


data: Dict = {
    "Accounts": [
        {"Name": "John Doe", "Balance": 1000, "Address": {"City": "New York"}},
        {"Name": "Jane Smith", "Balance": 2000},
        {"Name": "Jim Beam", "Balance": 500, "Address": {"City": "Chicago"}},
        {"Name": "Jill Hill", "Balance": 1500},
    ],
    "Account": {
        "Order": [
            {
                "Product": [
                    {"Price": 50, "Quantity": 5},
                    {"Price": 20, "Quantity": 1},
                    {"Price": 15, "Quantity": 4},
                ]
            },
            {
                "Product": [
                    {"Price": 30, "Quantity": 5},
                    {"Price": 40, "Quantity": 3},
                    {"Price": 25, "Quantity": 2},
                ]
            },
        ]
    },
}

json_data = json.dumps(data)


class TestJExprBuilder:

    # List of test cases
    test_cases = [
        {
            "name": "Sum of quantities",
            "expression_builder": jx.sum(JExpr("Account").Order.Product.Quantity),
            "expected_result": 20,
        },
        {
            "name": "Products with Price > 25",
            "expression_builder": JExpr("Account").Order.Product.filter(JExpr("Price") > 25),
            "expected_result": [
                {"Price": 50, "Quantity": 5},
                {"Price": 30, "Quantity": 5},
                {"Price": 40, "Quantity": 3},
            ],
        },
        {
            "name": "Total number of products",
            "expression_builder": jx.count(JExpr("Account").Order.Product),
            "expected_result": 6,
        },
        {
            "name": "Average price of products",
            "expression_builder": jx.average(JExpr("Account").Order.Product.Price),
            "expected_result": 30,
        },
        {
            "name": "Maximum price of products",
            "expression_builder": jx.max(JExpr("Account").Order.Product.Price),
            "expected_result": 50,
        },
        {
            "name": "Minimum price of products",
            "expression_builder": jx.min(JExpr("Account").Order.Product.Price),
            "expected_result": 15,
        },
        {
            "name": "Access root variable $",
            "expression_builder": JExpr("$").Account,
            "expected_result": data["Account"],
        },
        {
            "name": "Access second Order using [1]",
            "expression_builder": JExpr("Account").Order[1],
            "expected_result": data["Account"]["Order"][1],
        },
        {
            "name": "Products with Price > 20",
            "expression_builder": JExpr("Account").Order.Product.filter(JExpr("Price") > 20),
            "expected_result": [
                {"Price": 50, "Quantity": 5},
                {"Price": 30, "Quantity": 5},
                {"Price": 40, "Quantity": 3},
                {"Price": 25, "Quantity": 2},
            ],
        },
        {
            "name": "Products with Price > 20 and Quantity < 5",
            "expression_builder": JExpr("Account").Order.Product.filter(
                (JExpr("Price") > 20).and_(JExpr("Quantity") < 5)
            ),
            "expected_result": [
                {"Price": 40, "Quantity": 3},
                {"Price": 25, "Quantity": 2},
            ],
        },
        {
            "name": "Second Product in Each Order",
            "expression_builder": JExpr("Account").Order.Product[1],
            "expected_result": [
                {"Price": 20, "Quantity": 1},
                {"Price": 40, "Quantity": 3},
            ],
        },
        {
            "name": "Accounts with Name 'John Doe'",
            "expression_builder": JExpr("Accounts").filter(JExpr("Name") == "John Doe"),
            "expected_result": {
                "Name": "John Doe",
                "Balance": 1000,
                "Address": {"City": "New York"},
            },
        },
        {
            "name": "Accounts with Address",
            "expression_builder": JExpr("Accounts").filter(JExpr("Address")),
            "expected_result": [
                {"Name": "John Doe", "Balance": 1000, "Address": {"City": "New York"}},
                {"Name": "Jim Beam", "Balance": 500, "Address": {"City": "Chicago"}},
            ],
        },
        {
            "name": "Convert number to string",
            "expression_builder": jx.string(JExpr("Accounts")[0].Balance),
            "expected_result": "1000",
        },
        {
            "name": "Length of Name",
            "expression_builder": jx.length(JExpr("Accounts")[0].Name),
            "expected_result": 8,
        },
        {
            "name": "Substring of Name",
            "expression_builder": jx.substring(JExpr("Accounts")[0].Name, 0, 4),
            "expected_result": "John",
        },
        {
            "name": "Substring Before",
            "expression_builder": jx.substringBefore(JExpr("Accounts")[0].Name, " "),
            "expected_result": "John",
        },
        {
            "name": "Substring After",
            "expression_builder": jx.substringAfter(JExpr("Accounts")[0].Name, " "),
            "expected_result": "Doe",
        },
        {
            "name": "Uppercase Name",
            "expression_builder": jx.uppercase(JExpr("Accounts")[0].Name),
            "expected_result": "JOHN DOE",
        },
        {
            "name": "Lowercase Name",
            "expression_builder": jx.lowercase(JExpr("Accounts")[0].Name),
            "expected_result": "john doe",
        },
        {
            "name": "Trimmed String",
            "expression_builder": jx.trim(JExpr("'  Hello World  '")),
            "expected_result": "Hello World",
        },
        {
            "name": "Pad String",
            "expression_builder": jx.pad(JExpr("'Hello'"), 10, "*"),
            "expected_result": "Hello*****",
        },
        {
            "name": "Contains Substring",
            "expression_builder": jx.contains(JExpr("Accounts")[0].Name, "Doe"),
            "expected_result": True,
        },
        {
            "name": "Split String",
            "expression_builder": jx.split(JExpr("Accounts")[0].Name, " "),
            "expected_result": ["John", "Doe"],
        },
        {
            "name": "Join Strings",
            "expression_builder": jx.join(JExpr(["John", "Doe"]), " "),
            "expected_result": "John Doe",
        },
        {
            "name": "Replace Substring",
            "expression_builder": jx.replace(JExpr("Accounts")[0].Name, "John", "Jonathan"),
            "expected_result": "Jonathan Doe",
        },
        # New test data entries to add to the test case
        {
            "name": "Convert string to number",
            "expression_builder": jx.number(JExpr("'42'")),
            "expected_result": 42,
        },
        {
            "name": "Absolute value",
            "expression_builder": jx.abs(JExpr("-5")),
            "expected_result": 5,
        },
        {
            "name": "Floor function",
            "expression_builder": jx.floor(JExpr("3.7")),
            "expected_result": 3,
        },
        {
            "name": "Ceil function",
            "expression_builder": jx.ceil(JExpr("3.2")),
            "expected_result": 4,
        },
        {
            "name": "Round function",
            "expression_builder": jx.round(JExpr("3.14159"), 2),
            "expected_result": 3.14,
        },
        {
            "name": "Power function",
            "expression_builder": jx.power(JExpr("2"), JExpr("3")),
            "expected_result": 8,
        },
        {
            "name": "Square root function",
            "expression_builder": jx.sqrt(JExpr("16")),
            "expected_result": 4,
        },
        {
            "name": "Format base",
            "expression_builder": jx.formatBase(JExpr("255"), 16),
            "expected_result": "ff",
        },
        {
            "name": "Format integer to words",
            "expression_builder": jx.formatInteger(JExpr("123"), "w"),
            "expected_result": "one hundred and twenty-three",
        },
        {
            "name": "Format integer to Roman numerals",
            "expression_builder": jx.formatInteger(JExpr("1999"), "I"),
            "expected_result": "MCMXCIX",
        },
        {
            "name": "Parse integer from words",
            "expression_builder": jx.parseInteger(JExpr("'one hundred and twenty-three'"), "w"),
            "expected_result": 123,
        },
        {
            "name": "Parse integer from formatted string",
            "expression_builder": jx.parseInteger(JExpr("'12,345,678'"), "#,##0"),
            "expected_result": 12345678,
        },
        {
            "name": "Parse integer from Roman numerals",
            "expression_builder": jx.parseInteger(JExpr("'MCMXCIX'"), "I"),
            "expected_result": 1999,
        },
        # For $boolean()
        {
            "name": "Boolean of string 'false'",
            "expression_builder": jx.boolean(JExpr('"false"')),
            "expected_result": True,
        },
        {
            "name": "Boolean of empty string",
            "expression_builder": jx.boolean(JExpr('""')),
            "expected_result": False,
        },
        {
            "name": "Boolean of 1",
            "expression_builder": jx.boolean(JExpr("1")),
            "expected_result": True,
        },
        {
            "name": "Boolean of 0",
            "expression_builder": jx.boolean(JExpr("0")),
            "expected_result": False,
        },
        {
            "name": "Boolean of null",
            "expression_builder": jx.boolean(JExpr("null")),
            "expected_result": False,
        },
        {
            "name": "Boolean of non-empty array",
            "expression_builder": jx.boolean(JExpr("[1,2,3]")),
            "expected_result": True,
        },
        {
            "name": "Boolean of empty array",
            "expression_builder": jx.boolean(JExpr("[]")),
            "expected_result": False,
        },
        {
            "name": "Boolean of empty object",
            "expression_builder": jx.boolean(JExpr("{}")),
            "expected_result": False,
        },
        {
            "name": "Boolean of non-empty object",
            "expression_builder": jx.boolean(JExpr('{"key":"value"}')),
            "expected_result": True,
        },
        # For $not()
        {
            "name": "Not true",
            "expression_builder": jx.not_(JExpr("true")),
            "expected_result": False,
        },
        {
            "name": "Not false",
            "expression_builder": jx.not_(JExpr("false")),
            "expected_result": True,
        },
        {
            "name": "Not non-empty string",
            "expression_builder": jx.not_(JExpr('"abc"')),
            "expected_result": False,
        },
        {
            "name": "Not empty string",
            "expression_builder": jx.not_(JExpr('""')),
            "expected_result": True,
        },
        {
            "name": "Not 1",
            "expression_builder": jx.not_(JExpr("1")),
            "expected_result": False,
        },
        {
            "name": "Not 0",
            "expression_builder": jx.not_(JExpr("0")),
            "expected_result": True,
        },
        {
            "name": "Not null",
            "expression_builder": jx.not_(JExpr("null")),
            "expected_result": True,
        },
        {
            "name": "Not non-empty array",
            "expression_builder": jx.not_(JExpr("[1,2,3]")),
            "expected_result": False,
        },
        {
            "name": "Not empty array",
            "expression_builder": jx.not_(JExpr("[]")),
            "expected_result": True,
        },
        {
            "name": "Not empty object",
            "expression_builder": jx.not_(JExpr("{}")),
            "expected_result": True,
        },
        {
            "name": "Not non-empty object",
            "expression_builder": jx.not_(JExpr('{"key":"value"}')),
            "expected_result": False,
        },
        {
            "name": "Exists 5",
            "expression_builder": jx.exists(JExpr("5")),
            "expected_result": True,
        },
        {
            "name": "Exists null",
            "expression_builder": jx.exists(JExpr("null")),
            "expected_result": True,
        },
        {
            "name": "Exists non-empty array",
            "expression_builder": jx.exists(JExpr("[1,2,3]")),
            "expected_result": True,
        },
        {
            "name": "Exists empty array",
            "expression_builder": jx.exists(JExpr("[]")),
            "expected_result": True,
        },
        {
            "name": "Exists non-empty object",
            "expression_builder": jx.exists(JExpr('{"a":1}')),
            "expected_result": True,
        },
        {
            "name": "Exists empty object",
            "expression_builder": jx.exists(JExpr("{}")),
            "expected_result": True,
        },
        {
            "name": "Exists undefined variable",
            "expression_builder": jx.exists(JExpr("UndefinedVariable")),
            "expected_result": False,
        },
        {
            "name": "Exists NonExistentField in first account",
            "expression_builder": jx.exists(JExpr("Accounts[0].NonExistentField")),
            "expected_result": False,
        },
        {
            "name": "Exists Name in first account",
            "expression_builder": jx.exists(JExpr("Accounts[0].Name")),
            "expected_result": True,
        },
        # New test data entries to add to the test case
        # For $count()
        {
            "name": "Count of array [1,2,3]",
            "expression_builder": jx.count(JExpr("[1,2,3]")),
            "expected_result": 3,
        },
        {
            "name": "Count of number 5",
            "expression_builder": jx.count(JExpr("5")),
            "expected_result": 1,
        },
        {
            "name": "Count of empty array",
            "expression_builder": jx.count(JExpr("[]")),
            "expected_result": 0,
        },
        {
            "name": "Count of null",
            "expression_builder": jx.count(JExpr("null")),
            "expected_result": 0,
        },
        {
            "name": "Count of object",
            "expression_builder": jx.count(JExpr('{"a":1, "b":2}')),
            "expected_result": 1,
        },
        # For $append()
        {
            "name": "Append two arrays",
            "expression_builder": jx.append(JExpr("[1,2,3]"), JExpr("[4,5]")),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Append array and single value",
            "expression_builder": jx.append(JExpr("[1,2,3]"), JExpr("4")),
            "expected_result": [1, 2, 3, 4],
        },
        # For $sort()
        {
            "name": "Sort array of numbers",
            "expression_builder": jx.sort(JExpr("[5,3,1,4,2]")),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Sort array of strings",
            "expression_builder": jx.sort(JExpr('["zebra", "apple", "monkey"]')),
            "expected_result": ["apple", "monkey", "zebra"],
        },
        {
            "name": "Sort account balances",
            "expression_builder": jx.sort(JExpr("Accounts").Balance),
            "expected_result": [500, 1000, 1500, 2000],
        },
        # For $reverse()
        {
            "name": "Reverse array of numbers",
            "expression_builder": jx.reverse(JExpr("[1,2,3,4,5]")),
            "expected_result": [5, 4, 3, 2, 1],
        },
        {
            "name": "Reverse account names",
            "expression_builder": jx.reverse(JExpr("Accounts").Name),
            "expected_result": ["Jill Hill", "Jim Beam", "Jane Smith", "John Doe"],
        },
        # For $distinct()
        {
            "name": "Distinct values in array",
            "expression_builder": jx.distinct(JExpr("[1,2,3,2,4,1,5]")),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Distinct account balances",
            "expression_builder": jx.distinct(JExpr("[1000,2000,500,1500,1000,500]")),
            "expected_result": [1000, 2000, 500, 1500],
        },
        # For $zip()
        {
            "name": "Zip two arrays",
            "expression_builder": jx.zip(JExpr("[1,2,3],['a','b','c']")),
            "expected_result": [[1, "a"], [2, "b"], [3, "c"]],
        },
        {
            "name": "Zip account names and balances",
            "expression_builder": jx.zip(JExpr("Accounts.Name, Accounts.Balance")),
            "expected_result": [
                ["John Doe", 1000],
                ["Jane Smith", 2000],
                ["Jim Beam", 500],
                ["Jill Hill", 1500],
            ],
        },
        # New test data entries to add to the test case
        # For $keys()
        {
            "name": "Keys of an object",
            "expression_builder": jx.keys(JExpr('{"a":1, "b":2, "c":3}')),
            "expected_result": ["a", "b", "c"],
        },
        {
            "name": "Keys of first account",
            "expression_builder": jx.keys(JExpr("Accounts[0]")),
            "expected_result": ["Name", "Balance", "Address"],
        },
        # For $lookup()
        {
            "name": "Lookup value in object",
            "expression_builder": jx.lookup(JExpr('{"a":1, "b":2}'), JExpr('"b"')),
            "expected_result": 2,
        },
        {
            "name": "Lookup account by key",
            "expression_builder": jx.lookup(JExpr("Accounts[0]"), JExpr('"Name"')),
            "expected_result": "John Doe",
        },
        # For $spread()
        {
            "name": "Spread array of objects",
            "expression_builder": jx.spread(JExpr('[{"a":1, "b":2}, {"c":3}]')),
            "expected_result": [{"a": 1}, {"b": 2}, {"c": 3}],
        },
        {
            "name": "Spread accounts",
            "expression_builder": jx.spread(JExpr("Accounts")),
            "expected_result": [
                {"Name": "John Doe"},
                {"Balance": 1000},
                {"Address": {"City": "New York"}},
                {"Name": "Jane Smith"},
                {"Balance": 2000},
                {"Name": "Jim Beam"},
                {"Balance": 500},
                {"Address": {"City": "Chicago"}},
                {"Name": "Jill Hill"},
                {"Balance": 1500},
            ],
        },
        # For $merge()
        {
            "name": "Merge two objects",
            "expression_builder": jx.merge(JExpr('{"a":1}'), JExpr('{"b":2}')),
            "expected_result": {"a": 1, "b": 2},
        },
        {
            "name": "Merge multiple objects",
            "expression_builder": jx.merge(JExpr('{"a":1}'), JExpr('{"b":2}'), JExpr('{"c":3}')),
            "expected_result": {"a": 1, "b": 2, "c": 3},
        },
        # For $type()
        {
            "name": "Type of number",
            "expression_builder": jx.type(JExpr("42")),
            "expected_result": "number",
        },
        {
            "name": "Type of string",
            "expression_builder": jx.type(JExpr('"Hello"')),
            "expected_result": "string",
        },
        {
            "name": "Type of array",
            "expression_builder": jx.type(JExpr("[1,2,3]")),
            "expected_result": "array",
        },
        {
            "name": "Type of object",
            "expression_builder": jx.type(JExpr('{"a":1}')),
            "expected_result": "object",
        },
        {
            "name": "Type of boolean",
            "expression_builder": jx.type(JExpr("true")),
            "expected_result": "boolean",
        },
        {
            "name": "Type of null",
            "expression_builder": jx.type(JExpr("null")),
            "expected_result": "null",
        },
        {
            "name": "Now function",
            "expression_builder": jx.now(),
            "max_time_difference": 5,  # Allow a maximum difference of 5 seconds
        },
        {
            "name": "Millis function",
            "expression_builder": jx.millis(),
            "max_millis_difference": 5000,  # Allow a maximum difference of 5000 milliseconds (5 seconds)
        },
        {
            "name": "FromMillis function",
            "expression_builder": jx.fromMillis(JExpr("0")),
            "expected_result": "1970-01-01T00:00:00.000Z",
        },
        {
            "name": "ToMillis function",
            "expression_builder": jx.toMillis(JExpr('"1970-01-01T00:00:00.000Z"')),
            "expected_result": 0,
        },
        {
            "name": "Round-trip millis to timestamp",
            "expression_builder": jx.fromMillis(jx.toMillis(JExpr('"2020-01-01T00:00:00.000Z"'))),
            "expected_result": "2020-01-01T00:00:00.000Z",
        },
        # For $map()
        {
            "name": "Map multiply by 2",
            "expression_builder": jx.map(JExpr("[1,2,3,4]"), JFn(["$value"], JExpr("$value") * 2)),
            "expected_result": [2, 4, 6, 8],
        },
        {
            "name": "Map multiply by 2 using lambda",
            "expression_builder": jx.map(JExpr("[1,2,3,4]"), lambda value: value * 2),
            "expected_result": [2, 4, 6, 8],
        },
        # For $filter()
        {
            "name": "Filter even numbers",
            "expression_builder": jx.filter(JExpr("[1,2,3,4,5]"), JFn(["$value"], (JExpr("$value") % 2) == 0)),
            "expected_result": [2, 4],
        },
        # For $reduce()
        {
            "name": "Reduce sum",
            "expression_builder": jx.reduce(
                JArray([1, 2, 3, 4, 5]),
                JFn(["$accumulator", "$value"], JExpr("$accumulator") + JExpr("$value")),
                0,
            ),
            "expected_result": 15,
        },
        # For $sift() with function
        {
            "name": "Sift object with predicate function",
            "expression_builder": jx.sift(
                JExpr('{"a":1, "b":2, "c":3, "d":4}'),
                JFn(["$value", "$key"], (JExpr("$value") > 2)),
            ),
            "expected_result": {"c": 3, "d": 4},
        },
        # For $each() with function
        {
            "name": "Each over object with function",
            "expression_builder": jx.each(
                JObj({"a": 1, "b": 2}),
                JFn(
                    ["$value", "$key"],
                    JObj(
                        {
                            "k": JExpr("$key"),
                            "v": JExpr("$value") * 2,
                        }
                    ),
                ),
            ),
            "expected_result": [{"k": "a", "v": 2}, {"k": "b", "v": 4}],
        },
        {
            "name": "Each over object with function using lambda",
            "expression_builder": jx.each(JObj({"a": 1, "b": 2}), lambda value, key: {"k": key, "v": value * 2}),
            "expected_result": [{"k": "a", "v": 2}, {"k": "b", "v": 4}],
        },
        {
            "name": "Map to object with original and double values",
            "expression_builder": jx.map(
                JExpr("[1,2,3,4]"),
                JFn(
                    ["$value"],
                    JObj(
                        {
                            "original": JExpr("$value"),
                            "double": JExpr("$value") * 2,
                        }
                    ),
                ),
            ),
            "expected_result": [
                {"original": 1, "double": 2},
                {"original": 2, "double": 4},
                {"original": 3, "double": 6},
                {"original": 4, "double": 8},
            ],
        },
        {
            "name": "Order products by price",
            "expression_builder": JExpr("Account").Order.Product.order_by(JExpr("Price")),
            "expected_result": [
                {"Price": 15, "Quantity": 4},
                {"Price": 20, "Quantity": 1},
                {"Price": 25, "Quantity": 2},
                {"Price": 30, "Quantity": 5},
                {"Price": 40, "Quantity": 3},
                {"Price": 50, "Quantity": 5},
            ],
        },
        {
            "name": "Wildcard operator on first account",
            "expression_builder": JExpr("Accounts")[0].wildcard(),
            "expected_result": ["John Doe", 1000, {"City": "New York"}],
        },
        {
            "name": "Descendants of first account",
            "expression_builder": JExpr("Accounts")[0].descendants(),
            "expected_result": [
                {"Name": "John Doe", "Balance": 1000, "Address": {"City": "New York"}},
                "John Doe",
                1000,
                {"City": "New York"},
                "New York",
            ],
        },
        # Numeric Operators
        {
            "name": "Addition of numbers",
            "expression_builder": JExpr("5") + 3,
            "expected_result": 8,
        },
        {
            "name": "Addition of variables",
            "expression_builder": JExpr("Accounts[0].Balance") + JExpr("Accounts[1].Balance"),
            "expected_result": 3000,
        },
        {
            "name": "Subtraction of numbers",
            "expression_builder": JExpr("5") - 3,
            "expected_result": 2,
        },
        {
            "name": "Subtraction with variables",
            "expression_builder": JExpr("Accounts[1].Balance") - JExpr("Accounts[0].Balance"),
            "expected_result": 1000,
        },
        {
            "name": "Multiplication of numbers",
            "expression_builder": JExpr("5") * 3,
            "expected_result": 15,
        },
        {
            "name": "Multiplication with variables",
            "expression_builder": JExpr("Accounts[0].Balance") * 2,
            "expected_result": 2000,
        },
        {
            "name": "Division of numbers",
            "expression_builder": JExpr("6") / 3,
            "expected_result": 2,
        },
        {
            "name": "Division with variables",
            "expression_builder": JExpr("Accounts[0].Balance") / 2,
            "expected_result": 500,
        },
        {
            "name": "Modulo operation",
            "expression_builder": JExpr("5") % 2,
            "expected_result": 1,
        },
        {
            "name": "Modulo with variables",
            "expression_builder": JExpr("Accounts[0].Balance") % 300,
            "expected_result": 100,
        },
        {
            "name": "Unary minus",
            "expression_builder": -JExpr("5"),
            "expected_result": -5,
        },
        {
            "name": "Unary minus with variable",
            "expression_builder": -JExpr("Accounts[0].Balance"),
            "expected_result": -1000,
        },
        {
            "name": "Range operator from 1 to 5",
            "expression_builder": JExpr.range(1, 5),
            "expected_result": [1, 2, 3, 4, 5],
        },
        # Array Indexing
        {
            "name": "Access first element of array",
            "expression_builder": JExpr("[10,20,30,40,50]")[0],
            "expected_result": 10,
        },
        {
            "name": "Access second element of array",
            "expression_builder": JExpr("[10,20,30,40,50]")[1],
            "expected_result": 20,
        },
        # Equals
        {
            "name": "Equals operator with numbers",
            "expression_builder": JExpr("5") == 5,
            "expected_result": True,
        },
        {
            "name": "Equals operator with strings",
            "expression_builder": JExpr('"hello"') == "hello",
            "expected_result": True,
        },
        {
            "name": "Equals operator with variables",
            "expression_builder": JExpr("Accounts[0].Name") == "John Doe",
            "expected_result": True,
        },
        # Not Equals
        {
            "name": "Not equals operator with numbers",
            "expression_builder": JExpr("5") != 3,
            "expected_result": True,
        },
        {
            "name": "Not equals operator with strings",
            "expression_builder": JExpr('"hello"') != "world",
            "expected_result": True,
        },
        {
            "name": "Not equals operator with variables",
            "expression_builder": JExpr("Accounts[0].Name") != "Jane Smith",
            "expected_result": True,
        },
        # Greater Than
        {
            "name": "Greater than operator with numbers",
            "expression_builder": JExpr("5") > 3,
            "expected_result": True,
        },
        {
            "name": "Greater than operator with variables",
            "expression_builder": JExpr("Accounts[1].Balance") > JExpr("Accounts[0].Balance"),
            "expected_result": True,
        },
        # Less Than
        {
            "name": "Less than operator with numbers",
            "expression_builder": JExpr("3") < 5,
            "expected_result": True,
        },
        {
            "name": "Less than operator with variables",
            "expression_builder": JExpr("Accounts[0].Balance") < JExpr("Accounts[1].Balance"),
            "expected_result": True,
        },
        # Greater Than or Equals
        {
            "name": "Greater than or equals operator with numbers",
            "expression_builder": JExpr("5") >= 5,
            "expected_result": True,
        },
        {
            "name": "Greater than or equals operator with variables",
            "expression_builder": JExpr("Accounts[1].Balance") >= JExpr("Accounts[0].Balance"),
            "expected_result": True,
        },
        # Less Than or Equals
        {
            "name": "Less than or equals operator with numbers",
            "expression_builder": JExpr("5") <= 5,
            "expected_result": True,
        },
        {
            "name": "Less than or equals operator with variables",
            "expression_builder": JExpr("Accounts[0].Balance") <= JExpr("Accounts[1].Balance"),
            "expected_result": True,
        },
        # Inclusion (in)
        {
            "name": "In operator with numbers",
            "expression_builder": JExpr("3").in_(JExpr("[1,2,3,4,5]")),
            "expected_result": True,
        },
        {
            "name": "In operator with strings",
            "expression_builder": JExpr('"apple"').in_(JExpr('["apple","banana","cherry"]')),
            "expected_result": True,
        },
        {
            "name": "In operator with variables",
            "expression_builder": JExpr("Accounts[0].Name").in_(JExpr("Accounts.Name")),
            "expected_result": True,
        },
        {
            "name": "In operator with missing value",
            "expression_builder": JExpr("6").in_(JExpr("[1,2,3,4,5]")),
            "expected_result": False,
        },
        # Concatenation Operator
        {
            "name": "Concatenate two strings",
            "expression_builder": JExpr('"Hello "') & JExpr('"World!"'),
            "expected_result": "Hello World!",
        },
        {
            "name": "Concatenate string and number",
            "expression_builder": JExpr('"Number: "') & JExpr("42"),
            "expected_result": "Number: 42",
        },
        # Logical AND
        {
            "name": "Logical AND with true and true",
            "expression_builder": JExpr("true").and_(JExpr("true")),
            "expected_result": True,
        },
        # Logical OR
        {
            "name": "Logical OR with true and false",
            "expression_builder": JExpr("true").or_(JExpr("false")),
            "expected_result": True,
        },
        # Conditional Operator
        {
            "name": "Conditional operator true condition",
            "expression_builder": jx.ternary(JNum(5) > JNum(3), "Greater", "Lesser"),
            "expected_result": "Greater",
        },
        {
            "name": "Conditional operator false condition",
            "expression_builder": jx.ternary(JExpr("2") > 3, "Greater", "Lesser"),
            "expected_result": "Lesser",
        },
        {
            "name": "Match multiple occurrences of 'l' in 'Hello World'",
            "expression_builder": jx.match("Hello World", r"/l+/"),
            "expected_result": [
                {"match": "ll", "index": 2, "groups": []},
                {"match": "l", "index": 9, "groups": []},
            ],
        },
        {
            "name": "Match pattern with capturing groups",
            "expression_builder": jx.match(JExpr("'Hello World'"), "/(o)/"),
            "expected_result": [
                {"match": "o", "index": 4, "groups": ["o"]},
                {"match": "o", "index": 7, "groups": ["o"]},
            ],
        },
        {
            "name": "Match that returns no results",
            "expression_builder": jx.match(JExpr("'Hello World'"), "/z+/"),
            "expected_result": None,
        },
        {
            "name": "Base64 encode 'Hello World'",
            "expression_builder": jx.base64encode(JExpr('"Hello World"')),
            "expected_result": "SGVsbG8gV29ybGQ=",
        },
        {
            "name": "Base64 decode 'SGVsbG8gV29ybGQ='",
            "expression_builder": jx.base64decode(JExpr('"SGVsbG8gV29ybGQ="')),
            "expected_result": "Hello World",
        },
        {
            "name": "Encode URL component 'Hello, World!'",
            "expression_builder": jx.encodeUrlComponent(JExpr('"Hello, World!"')),
            "expected_result": "Hello%2C%20World!",
        },
        {
            "name": "Encode URL 'Hello, World!'",
            "expression_builder": jx.encodeUrl(JExpr('"Hello, World!"')),
            "expected_result": "Hello,%20World!",
        },
        {
            "name": "Decode URL component 'Hello%2C%20World%21'",
            "expression_builder": jx.decodeUrlComponent(JExpr('"Hello%2C%20World%21"')),
            "expected_result": "Hello, World!",
        },
        {
            "name": "Decode URL 'Hello,%20World!'",
            "expression_builder": jx.decodeUrl(JStr("Hello,%20World!")),
            "expected_result": "Hello, World!",
        },
        {
            "name": "Filter even numbers using lambda",
            "expression_builder": jx.filter(JExpr("[1, 2, 3, 4, 5]"), lambda value: value % 2 == 0),
            "expected_result": [2, 4],
        },
        {
            "name": "Map to nested arithmetic operation using lambda",
            "expression_builder": jx.map(JExpr("[1, 2, 3, 4]"), lambda value: (value + 1) * 3),
            "expected_result": [6, 9, 12, 15],
        },
        {
            "name": "Map over nested object properties using lambda",
            "expression_builder": jx.map(JExpr("Accounts"), lambda account: account.Balance * 2),
            "expected_result": [2000, 4000, 1000, 3000],
        },
        {
            "name": "Map with conditional expression using lambda",
            "expression_builder": jx.map(
                JExpr("[1, 2, 3, 4, 5]"),
                lambda value: jx.ternary(value % 2 == 0, "Even", "Odd"),
            ),
            "expected_result": ["Odd", "Even", "Odd", "Even", "Odd"],
        },
        {
            "name": "Map to object with multiple properties using lambda",
            "expression_builder": jx.map(
                JExpr("[1, 2, 3]"),
                lambda value: {"original": value, "squared": value * value},
            ),
            "expected_result": [
                {"original": 1, "squared": 1},
                {"original": 2, "squared": 4},
                {"original": 3, "squared": 9},
            ],
        },
        {
            "name": "Filter items greater than 3 using lambda with boolean logic",
            "expression_builder": jx.filter(JExpr("[1, 2, 3, 4, 5, 6]"), lambda value: value > 3),
            "expected_result": [4, 5, 6],
        },
        {
            "name": "Map concatenate strings using lambda",
            "expression_builder": jx.map(
                JExpr('["apple", "banana", "cherry"]'),
                lambda value: value & JStr(" pie"),
            ),
            "expected_result": ["apple pie", "banana pie", "cherry pie"],
        },
        {
            "name": "Map to transform complex objects using lambda",
            "expression_builder": jx.map(
                JExpr("Accounts"),
                lambda account: {
                    "Name": account.Name,
                    "DoubleBalance": account.Balance * 2,
                },
            ),
            "expected_result": [
                {"Name": "John Doe", "DoubleBalance": 2000},
                {"Name": "Jane Smith", "DoubleBalance": 4000},
                {"Name": "Jim Beam", "DoubleBalance": 1000},
                {"Name": "Jill Hill", "DoubleBalance": 3000},
            ],
        },
        {
            "name": "Filter items in list using lambda with 'in' operator",
            "expression_builder": jx.filter(JExpr("[1, 2, 3, 4, 5]"), lambda value: value.in_([2, 4, 6])),
            "expected_result": [2, 4],
        },
        {
            "name": "Map with unary minus operation using lambda",
            "expression_builder": jx.map(JExpr("[1, 2, 3, 4]"), lambda value: -value),
            "expected_result": [-1, -2, -3, -4],
        },
        {
            "name": "Flatten nested list using map with lambda",
            "expression_builder": jx.map(
                JExpr("[[1, 2], [3, 4], [5, 6]]"),
                lambda sublist: jx.sum(JExpr(sublist)),
            ),
            "expected_result": [3, 7, 11],
        },
        {
            "name": "Filter based on multiple conditions using lambda",
            "expression_builder": jx.filter(
                JExpr("Accounts"),
                lambda account: (account.Balance > 1000).and_(account.Name == JStr("Jane Smith")),
            ),
            "expected_result": {"Name": "Jane Smith", "Balance": 2000},
        },
        {
            "name": "Map with optional property handling using lambda",
            "expression_builder": jx.map(
                JExpr("Accounts"),
                lambda account: {
                    "Name": account.Name,
                    "City": jx.ternary(account.Address.City, account.Address.City, "Unknown"),
                },
            ),
            "expected_result": [
                {"Name": "John Doe", "City": "New York"},
                {"Name": "Jane Smith", "City": "Unknown"},
                {"Name": "Jim Beam", "City": "Chicago"},
                {"Name": "Jill Hill", "City": "Unknown"},
            ],
        },
        {
            "name": "Map with multiple transformations using lambda",
            "expression_builder": jx.map(JExpr("[1, 2, 3, 4]"), lambda value: value * 2 + 1),
            "expected_result": [3, 5, 7, 9],
        },
        {
            "name": "Test variable value assignment",
            "expression_builder": jx.assign(JExpr("$x"), 5),
            "expected_result": 5,
        },
        {
            "name": "Test variable value assignment with expression",
            "expression_builder": jx.assign(JExpr("$x"), JExpr("Accounts")[0].Balance),
            "expected_result": 1000,
        },
        {
            "name": "Test variable value assignment with lambda",
            "expression_builder": JxScript(jx.assign("$x", lambda x: x * 42), JExpr("$x(2)")),
            "expected_result": 84,
        },
    ]

    pyobj_test_cases = [
        {
            "name": "Trim string using Python object",
            "expression_builder": jx.trim("  Hello World  "),
            "expected_result": "Hello World",
        },
        {
            "name": "Boolean of empty array using Python object",
            "expression_builder": jx.boolean([]),
            "expected_result": False,
        },
        {
            "name": "Boolean of non-empty object using Python object",
            "expression_builder": jx.boolean({"key": "value"}),
            "expected_result": True,
        },
        {
            "name": "Not operation using Python object",
            "expression_builder": jx.not_(True),
            "expected_result": False,
        },
        {
            "name": "Exists operation on variable using Python object",
            "expression_builder": jx.exists("Accounts[0].Balance"),
            "expected_result": True,
        },
        {
            "name": "Append two arrays using Python objects",
            "expression_builder": jx.append([1, 2, 3], [4, 5]),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Sort array of numbers using Python object",
            "expression_builder": jx.sort([5, 3, 1, 4, 2]),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Reverse array of numbers using Python object",
            "expression_builder": jx.reverse([1, 2, 3, 4, 5]),
            "expected_result": [5, 4, 3, 2, 1],
        },
        {
            "name": "Distinct values in array using Python object",
            "expression_builder": jx.distinct([1, 2, 3, 2, 4, 1, 5]),
            "expected_result": [1, 2, 3, 4, 5],
        },
        {
            "name": "Keys of an object using Python object",
            "expression_builder": jx.keys({"a": 1, "b": 2, "c": 3}),
            "expected_result": ["a", "b", "c"],
        },
        {
            "name": "Merge two objects using Python objects",
            "expression_builder": jx.merge({"a": 1}, {"b": 2}),
            "expected_result": {"a": 1, "b": 2},
        },
        {
            "name": "Sum function using Python list",
            "expression_builder": jx.sum([1, 2, 3, 4]),
            "expected_result": 10,
        },
        {
            "name": "Boolean check for number 1 using Python object",
            "expression_builder": jx.boolean(1),
            "expected_result": True,
        },
        {
            "name": "Type of a Python number",
            "expression_builder": jx.type(42),
            "expected_result": "number",
        },
        {
            "name": "Base64 encode using Python string",
            "expression_builder": jx.base64encode("Hello World"),
            "expected_result": "SGVsbG8gV29ybGQ=",
        },
        {
            "name": "Encode URL component using Python string",
            "expression_builder": jx.encodeUrlComponent("Hello, World!"),
            "expected_result": "Hello%2C%20World!",
        },
        {
            "name": "Absolute value using Python number",
            "expression_builder": jx.abs(-5),
            "expected_result": 5,
        },
        {
            "name": "Floor function using Python float",
            "expression_builder": jx.floor(3.7),
            "expected_result": 3,
        },
        {
            "name": "Ceil function using Python float",
            "expression_builder": jx.ceil(3.2),
            "expected_result": 4,
        },
        {
            "name": "Round function using Python float with precision",
            "expression_builder": jx.round(3.14159, 2),
            "expected_result": 3.14,
        },
        {
            "name": "Replace substring using Python string",
            "expression_builder": jx.replace("Hello World", "World", "JSONata"),
            "expected_result": "Hello JSONata",
        },
        {
            "name": "Pad string using Python arguments",
            "expression_builder": jx.pad("Hello", 10, "*"),
            "expected_result": "Hello*****",
        },
        {
            "name": "Split string using Python string and separator",
            "expression_builder": jx.split("Hello World", " "),
            "expected_result": ["Hello", "World"],
        },
        {
            "name": "Join strings using Python list and separator",
            "expression_builder": jx.join(["apple", "banana", "cherry"], ", "),
            "expected_result": "apple, banana, cherry",
        },
        {
            "name": "Map multiply by 2 using Python list",
            "expression_builder": jx.map([1, 2, 3, 4], lambda value: value * 2),
            "expected_result": [2, 4, 6, 8],
        },
        {
            "name": "Filter even numbers using Python list and lambda",
            "expression_builder": jx.filter([1, 2, 3, 4, 5], lambda value: value % 2 == 0),
            "expected_result": [2, 4],
        },
        {
            "name": "Reduce sum using Python list and lambda",
            "expression_builder": jx.reduce([1, 2, 3, 4, 5], lambda acc, value: acc + value, 0),
            "expected_result": 15,
        },
        {
            "name": "Access field using Python string",
            "expression_builder": "Accounts[0].Name",
            "expected_result": "John Doe",
        },
        {
            "name": "Access nested property using Python object",
            "expression_builder": "Accounts[0].Address.City",
            "expected_result": "New York",
        },
    ]

    # Parameterize the test function using the list of new test cases
    @pytest.mark.parametrize("test_case", pyobj_test_cases, ids=[tc["name"] for tc in pyobj_test_cases])
    def test_jexpr_python_objects(self, test_case):
        expression_builder = test_case["expression_builder"]
        expected_result = test_case.get("expected_result")
        expected_type = test_case.get("expected_type")
        expected_error = test_case.get("expected_error")

        # Serialize the expression
        expression_string = (
            expression_builder.serialize() if isinstance(expression_builder, JExpr) else str(expression_builder)
        )

        # Execute the expression against the data
        try:
            result = execute_jexpr(expression_string, data)
            print(f"Expression: {expression_string} => Result: {result}")
            if expected_error:
                pytest.fail(f"Expected error '{expected_error}' but got result '{result}'")
            else:
                if expected_result is not None:
                    # Assert the result matches the expected result
                    assert result == expected_result
                elif expected_type is not None:
                    # Assert the result is of the expected type
                    assert isinstance(result, expected_type)
                else:
                    pytest.fail("No expected result or expected type specified")
        except Exception as e:
            if expected_error:
                # Check if the error message matches
                assert expected_error in str(e)
            else:
                pytest.fail(f"Unexpected error occurred: {e}")

    # Parameterize the test function using the list of test cases

    @pytest.mark.parametrize("test_case", test_cases, ids=[tc["name"] for tc in test_cases])
    def test_jexpr_expression(self, test_case):
        expression_builder = test_case["expression_builder"]
        expected_result = test_case.get("expected_result")
        expected_type = test_case.get("expected_type")
        expected_error = test_case.get("expected_error")
        max_time_difference = test_case.get("max_time_difference")
        max_millis_difference = test_case.get("max_millis_difference")
        # Serialize the expression
        expression_string = expression_builder.serialize()
        # Execute the expression against the data
        try:
            result = execute_jexpr(expression_string, data)
            print(f"Expression: {expression_string} => Result: {result}")
            if expected_error:
                pytest.fail(f"Expected error '{expected_error}' but got result '{result}'")
            else:
                if max_time_difference is not None:
                    # For date-time comparisons
                    now = datetime.now(timezone.utc)
                    result_time = parser.isoparse(result)
                    time_diff = abs((now - result_time).total_seconds())
                    assert (
                        time_diff <= max_time_difference
                    ), f"Time difference {time_diff} exceeds {max_time_difference}"
                elif max_millis_difference is not None:
                    # For millis comparisons
                    now_millis = int(datetime.now(timezone.utc).timestamp() * 1000)
                    time_diff = abs(now_millis - result)
                    assert (
                        time_diff <= max_millis_difference
                    ), f"Millis difference {time_diff} exceeds {max_millis_difference}"
                elif expected_result is None:
                    # Assert the response is None
                    assert result is None
                elif expected_result is not None:
                    # Assert the result matches the expected result
                    assert result == expected_result
                elif expected_type is not None:
                    # Assert the result is of the expected type
                    assert isinstance(result, expected_type)
                else:
                    pytest.fail("No expected result or expected type specified")
        except Exception as e:
            if expected_error:
                # Check if the error message matches
                assert expected_error in str(e)
            else:
                pytest.fail(f"Unexpected error occurred: {e}")
