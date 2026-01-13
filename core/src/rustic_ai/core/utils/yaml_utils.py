"""YAML utilities with modular loading support.

This module provides a custom YAML loader that supports:
- !include: Include other YAML files (with circular dependency detection)
- !code: Load file contents as raw strings

Security Considerations:
    This module is designed for use with TRUSTED configuration files only.
    It does not implement strict path sandboxing. Users processing untrusted
    YAML files should implement additional path validation in their application.
"""

from io import StringIO
import os
import threading
from typing import IO, Any, Optional, Type, Union

import yaml

# Thread-local storage for tracking include chains to detect circular dependencies
_include_stack = threading.local()


def _get_include_stack() -> list:
    """Get the current thread's include stack."""
    if not hasattr(_include_stack, "stack"):
        _include_stack.stack = []
    return _include_stack.stack


class YamlLoader(yaml.SafeLoader):
    """
    Custom YAML loader that supports !include and !code tags.

    The loader automatically determines ``root_path`` based on the ``stream``
    passed to ``__init__``: if the stream has a ``name`` attribute, its
    directory is used; otherwise, ``root_path`` defaults to the class-level
    value which is set by create_loader_class.

    Attributes:
        root_path: Directory used for resolving relative paths in !include and !code tags.
        validation_root: Root directory for security validation. All included files must
                         be within this directory. Defaults to root_path if not set.
    """

    root_path: str = "."
    validation_root: str = "."

    def __init__(self, stream):
        # Only override root_path if not already set at class level or if stream has a name
        if hasattr(stream, "name") and getattr(stream, "name"):
            self.root_path = os.path.dirname(os.path.abspath(stream.name))
        # Otherwise keep the class-level root_path (set by create_loader_class)
        super().__init__(stream)


def _validate_path(filename: str, loader_root: str) -> None:
    """Validate that the resolved path doesn't attempt directory traversal.

    This is a basic check that helps prevent obvious directory traversal attacks.
    For production use with untrusted input, implement stricter validation.

    Args:
        filename: The absolute path to validate
        loader_root: The root directory of the loader

    Raises:
        ValueError: If the path appears to use directory traversal patterns
    """
    # Basic security check - this is intentionally permissive since the module
    # is designed for trusted configuration files. More restrictive validation
    # can be added at the application level if needed for untrusted inputs.
    #
    # Ensure that the target file remains within the loader's root directory.
    if not loader_root:
        return

    abs_root = os.path.abspath(loader_root)
    abs_filename = os.path.abspath(filename)

    try:
        common = os.path.commonpath([abs_root, abs_filename])
    except ValueError as exc:
        # Raised if paths are on different drives or otherwise incomparable
        raise ValueError(f"Invalid include path '{filename}' relative to root '{loader_root}': {exc}") from exc

    if common != abs_root:
        raise ValueError(f"Included file '{filename}' is outside the allowed root directory '{loader_root}'.")


def construct_include(loader: YamlLoader, node: yaml.ScalarNode) -> Any:
    """Read a YAML file and return the parsed object.

    The !include tag is intended only for including other YAML/YML files.
    For including non-YAML files as raw text, use the !code tag instead.

    Args:
        loader: The YAML loader instance
        node: The scalar node containing the file path

    Returns:
        The parsed YAML content from the included file

    Raises:
        ValueError: If a circular include is detected or if the file is not YAML
        FileNotFoundError: If the referenced file cannot be found or read
    """
    filename = os.path.abspath(os.path.join(loader.root_path, loader.construct_scalar(node)))
    extension = os.path.splitext(filename)[1].lower()

    # Enforce YAML-only for !include
    if extension not in (".yaml", ".yml"):
        raise ValueError(
            f"!include only supports .yaml/.yml files, but got '{filename}'. "
            f"Use !code to include non-YAML files as text."
        )

    # Validate path for basic security - use validation_root which is preserved from top-level load
    validation_root = getattr(loader, "validation_root", loader.root_path)
    _validate_path(filename, validation_root)

    # Check for circular includes
    include_stack = _get_include_stack()
    if filename in include_stack:
        include_chain = " -> ".join(include_stack + [filename])
        raise ValueError(f"Circular YAML !include detected: {include_chain}")

    # Add to stack and load
    include_stack.append(filename)
    try:
        with open(filename, "r") as f:
            # Use the included file's directory as base for resolving its relative paths,
            # but pass the original validation_root for security validation
            return load_yaml(f, base_dir=os.path.dirname(filename), root_dir=validation_root)
    except OSError as exc:
        # Provide clear context about which file failed to load and from where
        source_stream = getattr(loader, "stream", None)
        source_name = getattr(source_stream, "name", None) if source_stream is not None else None
        if not source_name:
            source_name = loader.root_path
        raise FileNotFoundError(
            f"Error loading included file '{filename}' referenced from '{source_name}': {exc}"
        ) from exc
    finally:
        include_stack.pop()


def construct_code(loader: YamlLoader, node: yaml.ScalarNode) -> str:
    """Read a file and return its content as a string.

    The !code tag loads the entire contents of a file as a raw string,
    useful for loading prompts, scripts, or other text content.

    Args:
        loader: The YAML loader instance
        node: The scalar node containing the file path

    Returns:
        The raw file contents as a string

    Raises:
        FileNotFoundError: If the referenced file cannot be found or read
    """
    filename = os.path.abspath(os.path.join(loader.root_path, loader.construct_scalar(node)))

    # Validate path for basic security - use validation_root which is preserved from top-level load
    validation_root = getattr(loader, "validation_root", loader.root_path)
    _validate_path(filename, validation_root)

    try:
        with open(filename, "r") as f:
            return f.read()
    except OSError as exc:
        # Provide clear context about which file failed to load and from where
        source_stream = getattr(loader, "stream", None)
        source_name = getattr(source_stream, "name", None) if source_stream is not None else None
        if not source_name:
            source_name = loader.root_path
        raise FileNotFoundError(f"Error loading code file '{filename}' referenced from '{source_name}': {exc}") from exc


def _resolve_root_path(stream: Any, root_dir: Optional[str], base_dir: Optional[str] = None) -> str:
    """Resolve the root directory for relative path resolution.

    Args:
        stream: The YAML stream being loaded
        root_dir: Optional explicit root directory for security validation
        base_dir: Optional base directory for resolving relative paths

    Returns:
        The resolved root directory path
    """
    # Use base_dir if provided (for resolving relative paths in nested includes)
    if base_dir:
        return os.path.abspath(base_dir)
    if root_dir:
        return os.path.abspath(root_dir)
    if hasattr(stream, "name") and getattr(stream, "name"):
        return os.path.dirname(os.path.abspath(stream.name))
    return os.getcwd()


def create_loader_class(stream: Any, base_dir: Optional[str], root_dir: Optional[str] = None) -> Type[YamlLoader]:
    """Create a loader subclass configured with the correct root path.

    Args:
        stream: The YAML stream to load
        base_dir: Optional base directory for resolving relative paths
        root_dir: Optional root directory for security validation (defaults to base_dir)

    Returns:
        A YamlLoader subclass configured with the appropriate root path
    """

    class SpecificLoader(YamlLoader):
        pass

    # root_path is used for resolving relative paths in the YAML file
    SpecificLoader.root_path = _resolve_root_path(stream, root_dir, base_dir)
    # validation_root is used for security checks - files must be within this directory
    SpecificLoader.validation_root = os.path.abspath(root_dir) if root_dir else SpecificLoader.root_path
    SpecificLoader.add_constructor("!include", construct_include)
    SpecificLoader.add_constructor("!code", construct_code)

    return SpecificLoader


def load_yaml(stream: Union[IO[str], str], base_dir: Optional[str] = None, root_dir: Optional[str] = None) -> Any:
    """
    Load YAML with support for !include and !code tags.

    Args:
        stream: File stream or string content to parse
        base_dir: Base directory for resolving relative paths. If None, uses stream.name or cwd.
        root_dir: Root directory for security validation. Files must be within this directory.
                  If None, defaults to base_dir. This is preserved across nested includes.

    Returns:
        The parsed YAML data structure

    Raises:
        yaml.YAMLError: If the YAML content is malformed
        FileNotFoundError: If an !include or !code file cannot be found
        ValueError: If a circular !include is detected
        TypeError: If stream is neither a file object nor a string

    Note:
        When passing string content, base_dir should typically be provided
        to enable proper relative path resolution for !include and !code tags.
    """
    # Handle string input by wrapping in StringIO
    if isinstance(stream, str):
        stream = StringIO(stream)
        # If no base_dir provided for string content, use current directory
        if base_dir is None:
            base_dir = os.getcwd()

    loader_cls = create_loader_class(stream, base_dir, root_dir)
    loader = loader_cls(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()
