from typing import List

import jsonpatch
from pydantic import BaseModel, Field, JsonValue

from rustic_ai.core.state.updater.state_updater import StateUpdater
from rustic_ai.core.utils import JsonDict


class JsonPatchOperation(BaseModel):
    """
    A class to represent a JSON patch operation.
    """

    op: str
    path: str
    value: JsonValue


class JsonPatchUpdate(BaseModel):
    """
    A class to represent a JSON patch update.
    """

    operations: List[JsonPatchOperation] = Field(
        description="The operations to apply to the state.",
    )

    def get_ops(self) -> list:
        return [op.model_dump() for op in self.operations]


class JsonPatchUpdater(StateUpdater):
    """
    A class to apply a JSON patch to the state.
    """

    @staticmethod
    def apply_update(state: JsonDict, update: JsonDict) -> JsonDict:
        parsed_update = JsonPatchUpdate.model_validate(update)
        return jsonpatch.apply_patch(state, parsed_update.get_ops())
