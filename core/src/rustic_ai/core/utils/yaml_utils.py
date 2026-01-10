import os
from typing import IO, Any, Optional, Type, Union

import yaml


class YamlLoader(yaml.SafeLoader):
    """
    Custom YAML loader that supports !include and !code tags.
    Base implementation that needs a root_path injected.
    """

    root_path: str = "."

    def __init__(self, stream):
        try:
            self.root_path = os.path.dirname(getattr(stream, "name", "."))
        except AttributeError:
            self.root_path = "."
        super().__init__(stream)


def construct_include(loader: YamlLoader, node: yaml.ScalarNode) -> Any:
    """Read a YAML file and return the parsed object."""
    filename = os.path.abspath(os.path.join(loader.root_path, loader.construct_scalar(node)))
    extension = os.path.splitext(filename)[1].lower()

    with open(filename, "r") as f:
        if extension in (".yaml", ".yml"):
            return load_yaml(f, os.path.dirname(filename))
        else:
            # Fallback for non-yaml files if someone uses !include on them?
            # Or should we enforce !code?
            # For now, let's treat !include as "parse this structure"
            # If it's JSON it will parse as YAML which is compatible.
            loader_cls = create_loader_class(f, os.path.dirname(filename))
            return yaml.load(f, Loader=loader_cls)


def construct_code(loader: YamlLoader, node: yaml.ScalarNode) -> str:
    """Read a file and return its content as a string."""
    filename = os.path.abspath(os.path.join(loader.root_path, loader.construct_scalar(node)))
    with open(filename, "r") as f:
        return f.read()


def _resolve_root_path(stream: Any, root_dir: Optional[str]) -> str:
    if root_dir:
        return root_dir
    if hasattr(stream, "name") and getattr(stream, "name"):
        return os.path.dirname(os.path.abspath(stream.name))
    return os.getcwd()


def create_loader_class(stream: Any, root_dir: Optional[str]) -> Type[YamlLoader]:
    """Create a loader subclass configured with the correct root path."""

    class SpecificLoader(YamlLoader):
        pass

    SpecificLoader.root_path = _resolve_root_path(stream, root_dir)
    SpecificLoader.add_constructor("!include", construct_include)
    SpecificLoader.add_constructor("!code", construct_code)

    return SpecificLoader


def load_yaml(stream: Union[str, IO[str]], base_dir: Optional[str] = None) -> Any:
    """
    Load YAML with support for !include and !code tags.

    Args:
        stream: File stream or string content
        base_dir: Base directory for relative paths. If None, tries to use stream.name or cwd.
    """
    if isinstance(stream, str):
        # If it's a string, we treat it as content, not a filename
        # Wrapping it in class that behaves like stream so generic loader works?
        # Actually yaml.load accepts string or stream.
        pass

    loader_cls = create_loader_class(stream, base_dir)
    loader = loader_cls(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()
