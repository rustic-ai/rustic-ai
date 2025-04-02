# Wrapper function to automatically convert lambdas to JFn
import inspect
import json
from functools import wraps

from .jexpr import JAssignmernt, JExpr, JFn, _to_jexpr


def _lambda_to_jfn(lambda_func):
    if not callable(lambda_func):
        raise TypeError(f"Expected a callable function, got {type(lambda_func).__name__}")

    # Check if it's a lambda function
    if lambda_func.__name__ != "<lambda>":
        raise ValueError("Provided function must be a lambda function.")

    # Use inspect.signature to extract the parameters
    signature = inspect.signature(lambda_func)
    params = list(signature.parameters.keys())

    # Create JSONata-compliant parameter names
    jsonata_params = [f"${param}" for param in params]

    # We need to invoke the lambda with dummy arguments to get the body expression.
    # Use JExpr instances with parameter names to simulate the lambda invocation
    dummy_args = [JExpr(param) for param in jsonata_params]

    # Try to evaluate the lambda with JExpr arguments to construct a JExpr body
    try:
        body_expr = lambda_func(*dummy_args)

        # Convert the body to JExpr if needed
        body_expr = _to_jexpr(body_expr)

        if not isinstance(body_expr, JExpr):
            raise TypeError("Lambda function body must result in a JExpr instance.")
    except Exception as e:
        raise ValueError(f"Error while evaluating the lambda function: {e}")

    # Return a JFn with the JSONata-style parameters and the generated body expression
    return JFn(jsonata_params, body_expr)


def _wrap_with_lambda_support(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Convert any lambda function to JFn in the arguments
        new_args = []
        for arg in args:
            if inspect.isfunction(arg) and arg.__name__ == "<lambda>":
                arg = _lambda_to_jfn(arg)
            new_args.append(arg)
        return func(*new_args, **kwargs)

    return wrapper


def _wrap_with_conversion(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Convert arguments to JExpr if they aren't already
        new_args = [_to_jexpr(arg) if not isinstance(arg, JExpr) else arg for arg in args]
        new_kwargs = {k: _to_jexpr(v) if not isinstance(v, JExpr) else v for k, v in kwargs.items()}
        return func(*new_args, **new_kwargs)

    return wrapper


@_wrap_with_conversion
def sum(expression):
    return JExpr(f"$sum({expression.serialize()})")


@_wrap_with_conversion
def average(expression):
    return JExpr(f"$average({expression.serialize()})")


@_wrap_with_conversion
def max(expression):
    return JExpr(f"$max({expression.serialize()})")


@_wrap_with_conversion
def min(expression):
    return JExpr(f"$min({expression.serialize()})")


@_wrap_with_conversion
def count(expression):
    return JExpr(f"$count({expression.serialize()})")


@_wrap_with_conversion
def string(arg):
    return JExpr(f"$string({arg.serialize()})")


@_wrap_with_conversion
def length(arg):
    return JExpr(f"$length({arg.serialize()})")


@_wrap_with_conversion
def substring(string_expr, start, length=None):
    start_expr = start
    if length is not None:
        length_expr = length
        return JExpr(f"$substring({string_expr.serialize()}, {start_expr}, {length_expr})")
    else:
        return JExpr(f"$substring({string_expr.serialize()}, {start_expr})")


@_wrap_with_conversion
def substringBefore(string_expr, chars):
    return JExpr(f"$substringBefore({string_expr.serialize()}, {chars})")


@_wrap_with_conversion
def substringAfter(string_expr, chars):
    return JExpr(f"$substringAfter({string_expr.serialize()}, {chars})")


@_wrap_with_conversion
def uppercase(string_expr):
    return JExpr(f"$uppercase({string_expr.serialize()})")


@_wrap_with_conversion
def lowercase(string_expr):
    return JExpr(f"$lowercase({string_expr.serialize()})")


@_wrap_with_conversion
def trim(string_expr):
    return JExpr(f"$trim({string_expr.serialize()})")


@_wrap_with_conversion
def pad(string_expr, width, char=None):
    width_expr = width
    if char is not None:
        char_expr = char
        return JExpr(f"$pad({string_expr.serialize()}, {width_expr}, {char_expr})")
    else:
        return JExpr(f"$pad({string_expr.serialize()}, {width_expr})")


@_wrap_with_conversion
def contains(string_expr, substring):
    return JExpr(f"$contains({string_expr.serialize()}, {substring})")


@_wrap_with_conversion
def split(string_expr, separator=None, limit=None):
    args = [string_expr.serialize()]
    if separator is not None:
        args.append(separator.serialize())
    if limit is not None:
        args.append(limit.serliaze())
    args_str = ", ".join(args)
    return JExpr(f"$split({args_str})")


@_wrap_with_conversion
def join(array_expr, separator=None):
    if separator is not None:
        return JExpr(f"$join({array_expr.serialize()}, {separator})")
    else:
        return JExpr(f"$join({array_expr.serialize()})")


@_wrap_with_conversion
def replace(string_expr, pattern, replacement, limit=None):
    args = [string_expr.serialize(), pattern.serialize(), replacement.serialize()]
    if limit is not None:
        args.append(limit.serialize())
    args_str = ", ".join(args)
    return JExpr(f"$replace({args_str})")


@_wrap_with_conversion
def base64encode(binary_expr):
    return JExpr(f"$base64encode({binary_expr.serialize()})")


@_wrap_with_conversion
def base64decode(string_expr):
    return JExpr(f"$base64decode({string_expr.serialize()})")


@_wrap_with_conversion
def encodeUrlComponent(string_expr):
    return JExpr(f"$encodeUrlComponent({string_expr.serialize()})")


@_wrap_with_conversion
def encodeUrl(string_expr):
    return JExpr(f"$encodeUrl({string_expr.serialize()})")


@_wrap_with_conversion
def decodeUrlComponent(string_expr):
    return JExpr(f"$decodeUrlComponent({string_expr.serialize()})")


@_wrap_with_conversion
def decodeUrl(string_expr):
    return JExpr(f"$decodeUrl({string_expr.serialize()})")


@_wrap_with_conversion
def number(arg):
    return JExpr(f"$number({arg.serialize()})")


@_wrap_with_conversion
def abs(arg):
    return JExpr(f"$abs({arg.serialize()})")


@_wrap_with_conversion
def floor(arg):
    return JExpr(f"$floor({arg.serialize()})")


@_wrap_with_conversion
def ceil(arg):
    return JExpr(f"$ceil({arg.serialize()})")


@_wrap_with_conversion
def round(arg, precision=None):
    if precision is not None:
        return JExpr(f"$round({arg.serialize()}, {precision})")
    else:
        return JExpr(f"$round({arg.serialize()})")


@_wrap_with_conversion
def power(base, exponent):
    return JExpr(f"$power({base.serialize()}, {exponent.serialize()})")


@_wrap_with_conversion
def sqrt(arg):
    return JExpr(f"$sqrt({arg.serialize()})")


@_wrap_with_conversion
def formatNumber(number_expr, picture):
    return JExpr(f"$formatNumber({number_expr.serialize()}, {picture})")


@_wrap_with_conversion
def formatBase(number_expr, radix):
    return JExpr(f"$formatBase({number_expr.serialize()}, {radix})")


@_wrap_with_conversion
def formatInteger(number_expr, picture):
    return JExpr(f"$formatInteger({number_expr.serialize()}, {picture})")


@_wrap_with_conversion
def parseInteger(string_expr, picture):
    return JExpr(f"$parseInteger({string_expr.serialize()}, {picture})")


@_wrap_with_conversion
def boolean(arg):
    return JExpr(f"$boolean({arg.serialize()})")


@_wrap_with_conversion
def not_(arg):
    return JExpr(f"$not({arg.serialize()})")


@_wrap_with_conversion
def exists(arg):
    return JExpr(f"$exists({arg.serialize()})")


@_wrap_with_conversion
def append(array_expr1, array_expr2):
    return JExpr(f"$append({array_expr1.serialize()}, {array_expr2.serialize()})")


@_wrap_with_conversion
def sort(array_expr):
    return JExpr(f"$sort({array_expr.serialize()})")


@_wrap_with_conversion
def reverse(array_expr):
    return JExpr(f"$reverse({array_expr.serialize()})")


@_wrap_with_conversion
def shuffle(array_expr):
    return JExpr(f"$shuffle({array_expr.serialize()})")


@_wrap_with_conversion
def distinct(array_expr):
    return JExpr(f"$distinct({array_expr.serialize()})")


@_wrap_with_conversion
def zip(expr_of_arrays):
    return JExpr(f"$zip({expr_of_arrays.serialize()})")


@_wrap_with_conversion
def keys(obexpr):
    return JExpr(f"$keys({obexpr.serialize()})")


@_wrap_with_conversion
def lookup(obexpr, key_expr):
    return JExpr(f"$lookup({obexpr.serialize()}, {key_expr.serialize()})")


@_wrap_with_conversion
def spread(array_of_objects_expr):
    return JExpr(f"$spread({array_of_objects_expr.serialize()})")


@_wrap_with_conversion
def merge(*object_exprs):
    serialized_objects = ", ".join(obj.serialize() for obj in object_exprs)
    return JExpr(f"$merge([{serialized_objects}])")


@_wrap_with_conversion
def type(value_expr):
    return JExpr(f"$type({value_expr.serialize()})")


@_wrap_with_conversion
def now():
    return JExpr("$now()")


@_wrap_with_conversion
def millis():
    return JExpr("$millis()")


@_wrap_with_conversion
def fromMillis(millis_expr):
    return JExpr(f"$fromMillis({millis_expr.serialize()})")


@_wrap_with_conversion
def toMillis(timestamp_expr):
    return JExpr(f"$toMillis({timestamp_expr.serialize()})")


@_wrap_with_lambda_support
@_wrap_with_conversion
def map(array_expr, function_expr):
    return JExpr(f"$map({array_expr.serialize()}, {function_expr.serialize()})")


@_wrap_with_lambda_support
@_wrap_with_conversion
def filter(array_expr, function_expr):
    return JExpr(f"$filter({array_expr.serialize()}, {function_expr.serialize()})")


@_wrap_with_lambda_support
@_wrap_with_conversion
def reduce(array_expr, function_expr, initial_value):
    init_value = initial_value
    return JExpr(f"$reduce({array_expr.serialize()}, {function_expr.serialize()}, {init_value})")


@_wrap_with_lambda_support
@_wrap_with_conversion
def sift(obexpr, function_expr=None):
    if function_expr is not None:
        return JExpr(f"$sift({obexpr.serialize()}, {function_expr.serialize()})")
    else:
        return JExpr(f"$sift({obexpr.serialize()})")


@_wrap_with_lambda_support
@_wrap_with_conversion
def each(obexpr, function_expr=None):
    if function_expr is not None:
        return JExpr(f"$each({obexpr.serialize()}, {function_expr.serialize()})")
    else:
        return JExpr(f"$each({obexpr.serialize()})")


@_wrap_with_conversion
def match(string_expr, pattern, limit=None):
    strexpr = string_expr.serialize()
    pattern = json.loads(pattern.__str__())
    if limit is not None:
        return JExpr(f"$match({strexpr}, {pattern}, {limit})")
    else:
        return JExpr(f"$match({strexpr}, {pattern})")


@_wrap_with_conversion
def ternary(condition, true_expr, false_expr):
    true_str = true_expr.serialize()
    false_str = false_expr.serialize()
    return JExpr(f"({condition.serialize()}) ? {true_str} : {false_str}")


@_wrap_with_lambda_support
@_wrap_with_conversion
def assign(var_expr, value):
    value = _to_jexpr(value).serialize()
    return JAssignmernt(var_expr, value)
