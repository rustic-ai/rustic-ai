from typing import Dict

from jsonpath_ng.ext import parse
from pydantic import JsonValue

JsonDict = Dict[str, JsonValue]


class JsonUtils:
    @staticmethod
    def read_from_path(data: JsonDict, path: str) -> JsonDict:
        """
        Get the value of the path in the data.

        Args:
            data: The data to get the value from.
            path: Json Path to get the value.

        Returns:
            The value of the path in the data.
        """
        expr = parse(path)
        matches = expr.find(data)
        value = [match.value for match in matches][0] if matches else None
        return {expr.right.fields[0]: value}

    @staticmethod
    def update_at_path(state: JsonDict, path: str, value: JsonValue) -> JsonDict:
        """
        Update the value of the path in the data.

        Args:
            data: The data to update the value.
            path: Json Path to update the value.
            value: The value to update.
        """
        expr = parse(path)
        updated = expr.update(state, value)
        return updated
