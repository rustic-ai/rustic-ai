import logging
from typing import Dict, Optional

from jsonpath_ng.ext import parse
from jsonpath_ng.exceptions import JsonPathParserError
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
        Update the value at the specified JSON path in the state.

        Args:
            state: The JSON state to update.
            path: JSONPath expression to locate where to update.
            value: The value to set at the specified path.

        Returns:
            A new dictionary with the updated value. The original state is not modified.
            
        Raises:
            JsonPathParserError: If the path syntax is invalid.
            ValueError: If the update operation fails.
        """
        try:
            expr = parse(path)
            logging.debug(f"Updating JSONPath '{path}' with value type: {type(value).__name__}")
            updated = expr.update(state, value)
            
            # Check if the update actually happened (jsonpath-ng returns original state if path doesn't exist)
            if updated == state and JsonUtils.read_from_path(state, path) is None:
                # Path doesn't exist, create intermediate structure manually
                # For simple dot-notation paths like "agents.health"
                import copy
                from typing import cast
                result = copy.deepcopy(state)
                
                # Split the path and create nested structure
                path_parts = path.split('.')
                current: JsonDict = result
                
                # Create intermediate dictionaries
                for part in path_parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    # Ensure current[part] is a dictionary before proceeding
                    if not isinstance(current[part], dict):
                        raise ValueError(f"Cannot set nested path '{path}': intermediate path '{part}' is not a dictionary")
                    current = cast(JsonDict, current[part])
                
                # Set the final value
                current[path_parts[-1]] = value
                updated = result
            
            logging.debug(f"Successfully updated path '{path}'")
            return updated
        except JsonPathParserError as e:
            raise JsonPathParserError(f"Invalid JSONPath syntax '{path}': {e}")
        except Exception as e:
            raise ValueError(f"Failed to update path '{path}': {e}")
