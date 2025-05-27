from __future__ import annotations

import importlib
from types import ModuleType
from typing import (
    Annotated,
    Any,
    Type,
    TypeVar,
    cast,
)

from pydantic import BaseModel, PlainSerializer
from pydantic.functional_validators import BeforeValidator


def cls_to_path(cls: Type[BaseModel]) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def path_to_cls(value: Any) -> Type[BaseModel]:
    # ── NEW: short-circuit if we already have a model class ──
    if isinstance(value, type) and issubclass(value, BaseModel):
        return cast(Type[BaseModel], value)

    # the rest is unchanged: we expect a fully-qualified string
    if not isinstance(value, str):
        raise TypeError(
            "parameter_class must be a fully-qualified string or a "
            "subclass of pydantic.BaseModel; got "
            f"{type(value).__name__}"
        )

    module_path, _, qualname = value.rpartition(".")
    if not module_path:
        raise ValueError(f"Not a fully-qualified path: {value!r}")

    mod: ModuleType = importlib.import_module(module_path)

    obj: Any = mod
    for attr in qualname.split("."):
        obj = getattr(obj, attr)

    if not isinstance(obj, type):
        raise TypeError(f"{value!r} does not resolve to a class")

    if not issubclass(obj, BaseModel):
        raise TypeError(f"{value!r} is not a Pydantic model")

    return cast(Type[BaseModel], obj)


# reusable “model-class” alias that keeps the *generic* parameter
TParams = TypeVar("TParams", bound=BaseModel)

ModelClass = Annotated[
    Type[TParams],
    PlainSerializer(cls_to_path, return_type=str),
    BeforeValidator(path_to_cls),
]
