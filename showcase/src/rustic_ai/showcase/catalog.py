"""Load checked-in showcase blueprints from source or installed wheel resources."""

from importlib.resources import files
from importlib.resources.abc import Traversable
import json
from pathlib import Path
from typing import Any, Iterator


def _catalog_root() -> Traversable:
    packaged = files("rustic_ai.showcase").joinpath("apps")
    if packaged.is_dir():
        return packaged
    # Editable installations expose src/, while the authoring catalog is kept
    # once at the project root. Wheels map that same directory into the package.
    source = Path(__file__).resolve().parents[3] / "apps"
    if source.is_dir():
        return source
    raise FileNotFoundError("Showcase catalog resources are missing")


def _entries(root: Traversable, prefix: str = "") -> Iterator[str]:
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        name = prefix + entry.name
        if entry.is_dir():
            yield from _entries(entry, name + "/")
        elif entry.name.endswith(".json"):
            value = json.loads(entry.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("spec"), dict):
                yield name


def list_blueprints() -> tuple[str, ...]:
    """Return canonical catalog paths, including nested blueprint directories."""
    return tuple(_entries(_catalog_root()))


def load_blueprint(name: str) -> dict[str, Any]:
    """Read a catalog envelope by its canonical path; reject unknown paths."""
    if name not in list_blueprints():
        raise FileNotFoundError(f"Unknown showcase blueprint: {name}")
    value = _catalog_root().joinpath(*name.split("/")).read_text(encoding="utf-8")
    return json.loads(value)
