import copy
import logging
from typing import Any, Dict, Optional

from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse
from jsonpath_ng.jsonpath import Fields, Index, Root
from pydantic import JsonValue

JsonDict = Dict[str, JsonValue]


class JsonUtils:
    @staticmethod
    def read_from_path(data: JsonDict, path: str) -> Optional[JsonValue]:
        """
        Get the value at the specified JSON path in the data.

        Args:
            data: The JSON data to read from.
            path: JSONPath expression to locate the value.

        Returns:
            The value found at the path, or None if path doesn't exist.

        Raises:
            JsonPathParserError: If the path syntax is invalid.
            ValueError: If the path expression is malformed.
        """
        try:
            expr = parse(path)
            matches = expr.find(data)
            return matches[0].value if matches else None
        except JsonPathParserError as e:
            raise JsonPathParserError(f"Invalid JSONPath syntax '{path}': {e}")
        except (AttributeError, IndexError) as e:
            raise ValueError(f"Malformed path expression '{path}': {e}")

    @staticmethod
    def update_at_path(state: JsonDict, path: str, value: JsonValue) -> JsonDict:
        """
        Update the value at the specified JSON path in the state, creating missing intermediate paths.
        Supports both dot and bracket notation.

        Args:
            state: The JSON data to update.
            path: JSONPath expression to locate the update position.
            value: The value to set at the specified path.

        Returns:
            A new dictionary with the updated value.

        Examples:
            >>> state = {"user": {"name": "John"}}
            >>> JsonUtils.update_at_path(state, "$.user.age", 30)
            {"user": {"name": "John", "age": 30}}

            >>> JsonUtils.update_at_path({}, "$.users[0].name", "Alice")
            {"users": [{"name": "Alice"}]}

        Raises:
            JsonPathParserError: If the path syntax is invalid.
            ValueError: If the path expression is malformed or state is invalid.
        """
        # Input validation
        if not isinstance(state, dict):
            raise ValueError(f"State must be a dictionary, got {type(state).__name__}")
        if not path or not isinstance(path, str):
            raise ValueError("Path must be a non-empty string")

        try:
            expr = parse(path)
            logging.debug(f"Updating JSONPath '{path}' with value type: {type(value).__name__}")

            # Try direct update first
            updated = expr.update(copy.deepcopy(state), value)

            # If direct update worked, return it
            if updated != state:
                logging.debug(f"Successfully updated path '{path}' via direct update")
                return updated

            # Otherwise, create missing structure
            logging.debug(f"Direct update failed for '{path}', creating missing structure")
            return JsonUtils._create_missing_path_structure(state, expr, value, path)

        except JsonPathParserError as e:
            raise JsonPathParserError(f"Invalid JSONPath syntax '{path}': {e}")
        except Exception as e:
            raise ValueError(f"Failed to update path '{path}': {e}")

    @staticmethod
    def _create_missing_path_structure(state: JsonDict, expr, value: JsonValue, path: str) -> JsonDict:
        """
        Helper method to create missing path structure when direct update fails.

        Args:
            state: The original state dictionary.
            expr: Parsed JSONPath expression.
            value: The value to set.
            path: Original path string for error reporting.

        Returns:
            Updated dictionary with missing structure created.
        """
        result = copy.deepcopy(state)
        current = result
        segments = JsonUtils._decompose_jsonpath(expr)

        # Navigate through all segments except the last one
        for i, segment in enumerate(segments[:-1]):
            next_segment = segments[i + 1] if i + 1 < len(segments) else None
            is_next_index = isinstance(next_segment, int)

            if isinstance(segment, int):
                current = JsonUtils._handle_list_segment(current, segment, is_next_index, path)
            else:
                current = JsonUtils._handle_dict_segment(current, segment, is_next_index, path)

        # Handle final assignment
        JsonUtils._assign_final_value(current, segments[-1], value, path)

        return result

    @staticmethod
    def _decompose_jsonpath(expr) -> list:
        """
        Decompose JSONPath expression into a list of segments.

        Args:
            expr: Parsed JSONPath expression.

        Returns:
            List of path segments (strings for keys, integers for indices).
        """
        segments = []

        def decompose(node):
            if isinstance(node, Fields):
                segments.extend(node.fields)
            elif isinstance(node, Index):
                segments.append(node.index)
            elif hasattr(node, "left") and hasattr(node, "right"):
                decompose(node.left)
                decompose(node.right)
            elif hasattr(node, "child"):
                decompose(node.child)
            elif isinstance(node, Root):
                pass  # skip the root node
            else:
                raise ValueError(f"Unsupported JSONPath node: {type(node).__name__}")

        decompose(expr)
        return segments

    @staticmethod
    def _handle_list_segment(current, segment: int, is_next_index: bool, path: str):
        """
        Handle navigation through a list segment, creating structure as needed.

        Args:
            current: Current position in the data structure.
            segment: List index to navigate to.
            is_next_index: Whether the next segment is also an index.
            path: Original path for error reporting.

        Returns:
            The container at the segment position.
        """
        if not isinstance(current, list):
            raise ValueError(f"Expected list at segment index {segment} in path '{path}', got {type(current).__name__}")

        # Extend list if needed with appropriate default values
        default_value: Any = [] if is_next_index else {}
        while len(current) <= segment:
            current.append(default_value)

        # Ensure the element at this position is a container
        if not isinstance(current[segment], (dict, list)):
            current[segment] = [] if is_next_index else {}

        return current[segment]

    @staticmethod
    def _handle_dict_segment(current, segment: str, is_next_index: bool, path: str):
        """
        Handle navigation through a dictionary segment, creating structure as needed.

        Args:
            current: Current position in the data structure.
            segment: Dictionary key to navigate to.
            is_next_index: Whether the next segment is an index.
            path: Original path for error reporting.

        Returns:
            The container at the segment key.
        """
        if not isinstance(current, dict):
            raise ValueError(
                f"Expected dictionary at segment '{segment}' in path '{path}', got {type(current).__name__}"
            )

        # Create missing key with appropriate container type
        if segment not in current or not isinstance(current[segment], (dict, list)):
            current[segment] = [] if is_next_index else {}

        return current[segment]

    @staticmethod
    def _assign_final_value(current, last_segment, value: JsonValue, path: str):
        """
        Assign the final value to the target location.

        Args:
            current: Current position in the data structure.
            last_segment: Final segment (key or index).
            value: Value to assign.
            path: Original path for error reporting.
        """
        if isinstance(last_segment, int):
            if not isinstance(current, list):
                raise ValueError(
                    f"Expected list at final segment index {last_segment} in path '{path}', got {type(current).__name__}"
                )

            # Extend list if needed
            while len(current) <= last_segment:
                current.append(None)
            current[last_segment] = value
        else:
            if not isinstance(current, dict):
                raise ValueError(
                    f"Expected dictionary at final segment '{last_segment}' in path '{path}', got {type(current).__name__}"
                )
            current[last_segment] = value
