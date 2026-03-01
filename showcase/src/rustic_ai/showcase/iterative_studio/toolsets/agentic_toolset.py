"""Agentic Toolset - File operations and web search tools.

This toolset provides tools for the Agentic mode:
- ReadFile: Read contents of a file
- WriteFile: Write content to a file
- ApplyDiff: Apply a unified diff to a file
- ListDirectory: List files in a directory
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset


class ReadFileParams(BaseModel):
    """Parameters for the ReadFile tool."""

    file_path: str = Field(
        description="Path to the file to read, relative to the working directory"
    )
    start_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Starting line number (1-indexed). If not specified, reads from the beginning.",
    )
    end_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Ending line number (1-indexed, inclusive). If not specified, reads to the end.",
    )


class WriteFileParams(BaseModel):
    """Parameters for the WriteFile tool."""

    file_path: str = Field(
        description="Path to the file to write, relative to the working directory"
    )
    content: str = Field(
        description="Content to write to the file"
    )
    create_directories: bool = Field(
        default=True,
        description="Create parent directories if they don't exist",
    )


class ApplyDiffParams(BaseModel):
    """Parameters for the ApplyDiff tool."""

    file_path: str = Field(
        description="Path to the file to modify, relative to the working directory"
    )
    old_content: str = Field(
        description="The exact content to find and replace (must match exactly)"
    )
    new_content: str = Field(
        description="The new content to replace the old content with"
    )


class ListDirectoryParams(BaseModel):
    """Parameters for the ListDirectory tool."""

    directory_path: str = Field(
        default=".",
        description="Path to the directory to list, relative to the working directory",
    )
    recursive: bool = Field(
        default=False,
        description="Whether to list files recursively",
    )
    pattern: Optional[str] = Field(
        default=None,
        description="Glob pattern to filter files (e.g., '*.py', '**/*.json')",
    )


class AgenticToolset(ReActToolset):
    """
    A ReActToolset providing file operations for the Agentic mode.

    This toolset provides tools for reading and writing files, applying
    diffs, and listing directory contents. It operates within a sandboxed
    working directory that is set via bind_agent_context.

    Example usage in guild spec:
        properties:
          toolset:
            kind: rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset.AgenticToolset
            working_dir: "/tmp/iterative_studio"
    """

    working_dir: str = Field(
        default="/tmp/iterative_studio",
        description="Base working directory for file operations",
    )

    # Internal: Set by bind_agent_context
    _guild_working_dir: Optional[str] = None

    def bind_agent_context(self, org_id: str, guild_id: str, agent_id: str) -> None:
        """Configure toolset with guild-specific working directory."""
        # Create a guild-specific subdirectory
        base = Path(self.working_dir)
        guild_dir = base / guild_id
        guild_dir.mkdir(parents=True, exist_ok=True)
        self._guild_working_dir = str(guild_dir)

    def _get_working_dir(self) -> Path:
        """Get the effective working directory."""
        if self._guild_working_dir:
            return Path(self._guild_working_dir)
        return Path(self.working_dir)

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a file path relative to the working directory, preventing directory traversal."""
        working_dir = self._get_working_dir()
        resolved = (working_dir / file_path).resolve()

        # Security: Ensure the resolved path is within the working directory
        if not str(resolved).startswith(str(working_dir.resolve())):
            raise ValueError(f"Path '{file_path}' is outside the allowed working directory")

        return resolved

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return the list of tool specifications available in this toolset."""
        return [
            ToolSpec(
                name="ReadFile",
                description=(
                    "Read the contents of a file. Optionally specify line ranges to read "
                    "a portion of the file. Returns the file content with line numbers."
                ),
                parameter_class=ReadFileParams,
            ),
            ToolSpec(
                name="WriteFile",
                description=(
                    "Write content to a file. Creates the file if it doesn't exist. "
                    "Optionally creates parent directories."
                ),
                parameter_class=WriteFileParams,
            ),
            ToolSpec(
                name="ApplyDiff",
                description=(
                    "Apply a text replacement to a file. Finds the exact old_content "
                    "and replaces it with new_content. Useful for targeted code changes."
                ),
                parameter_class=ApplyDiffParams,
            ),
            ToolSpec(
                name="ListDirectory",
                description=(
                    "List files in a directory. Can list recursively and filter by "
                    "glob patterns. Returns file paths and basic metadata."
                ),
                parameter_class=ListDirectoryParams,
            ),
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """Execute a tool by name with the given arguments."""
        try:
            if tool_name == "ReadFile" and isinstance(args, ReadFileParams):
                return self._read_file(args)
            elif tool_name == "WriteFile" and isinstance(args, WriteFileParams):
                return self._write_file(args)
            elif tool_name == "ApplyDiff" and isinstance(args, ApplyDiffParams):
                return self._apply_diff(args)
            elif tool_name == "ListDirectory" and isinstance(args, ListDirectoryParams):
                return self._list_directory(args)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _read_file(self, params: ReadFileParams) -> str:
        """Read file contents with optional line range."""
        path = self._resolve_path(params.file_path)

        if not path.exists():
            return json.dumps({"error": f"File not found: {params.file_path}"})

        if not path.is_file():
            return json.dumps({"error": f"Not a file: {params.file_path}"})

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Apply line range if specified
            start_idx = (params.start_line - 1) if params.start_line else 0
            end_idx = params.end_line if params.end_line else len(lines)

            # Clamp to valid range
            start_idx = max(0, min(start_idx, len(lines)))
            end_idx = max(start_idx, min(end_idx, len(lines)))

            selected_lines = lines[start_idx:end_idx]

            # Format with line numbers
            formatted_lines = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:4d} | {line.rstrip()}")

            return json.dumps(
                {
                    "file_path": params.file_path,
                    "total_lines": len(lines),
                    "showing_lines": f"{start_idx + 1}-{end_idx}",
                    "content": "\n".join(formatted_lines),
                },
                indent=2,
            )
        except UnicodeDecodeError:
            return json.dumps({"error": f"File is not a text file: {params.file_path}"})

    def _write_file(self, params: WriteFileParams) -> str:
        """Write content to a file."""
        path = self._resolve_path(params.file_path)

        if params.create_directories:
            path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(params.content)

        return json.dumps(
            {
                "success": True,
                "file_path": params.file_path,
                "bytes_written": len(params.content.encode("utf-8")),
            },
            indent=2,
        )

    def _apply_diff(self, params: ApplyDiffParams) -> str:
        """Apply a text replacement to a file."""
        path = self._resolve_path(params.file_path)

        if not path.exists():
            return json.dumps({"error": f"File not found: {params.file_path}"})

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if params.old_content not in content:
            return json.dumps(
                {
                    "error": "The specified old_content was not found in the file",
                    "hint": "Make sure the old_content matches exactly, including whitespace and line endings",
                }
            )

        # Count occurrences
        occurrences = content.count(params.old_content)
        if occurrences > 1:
            return json.dumps(
                {
                    "error": f"Found {occurrences} occurrences of old_content. Please provide more context to make it unique.",
                }
            )

        # Apply the replacement
        new_content = content.replace(params.old_content, params.new_content, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return json.dumps(
            {
                "success": True,
                "file_path": params.file_path,
                "message": "Replacement applied successfully",
            },
            indent=2,
        )

    def _list_directory(self, params: ListDirectoryParams) -> str:
        """List files in a directory."""
        path = self._resolve_path(params.directory_path)

        if not path.exists():
            return json.dumps({"error": f"Directory not found: {params.directory_path}"})

        if not path.is_dir():
            return json.dumps({"error": f"Not a directory: {params.directory_path}"})

        files: List[dict] = []

        if params.pattern:
            # Use glob pattern
            glob_method = path.rglob if params.recursive else path.glob
            for item in glob_method(params.pattern):
                if item.is_file():
                    rel_path = item.relative_to(path)
                    files.append(
                        {
                            "path": str(rel_path),
                            "size": item.stat().st_size,
                            "type": "file",
                        }
                    )
        else:
            # List all entries
            if params.recursive:
                for root, dirs, filenames in os.walk(path):
                    root_path = Path(root)
                    for d in dirs:
                        rel_path = (root_path / d).relative_to(path)
                        files.append({"path": str(rel_path), "type": "directory"})
                    for f in filenames:
                        item = root_path / f
                        rel_path = item.relative_to(path)
                        files.append(
                            {
                                "path": str(rel_path),
                                "size": item.stat().st_size,
                                "type": "file",
                            }
                        )
            else:
                for item in path.iterdir():
                    entry = {
                        "path": item.name,
                        "type": "directory" if item.is_dir() else "file",
                    }
                    if item.is_file():
                        entry["size"] = item.stat().st_size
                    files.append(entry)

        # Sort files by path
        files.sort(key=lambda x: x["path"])

        return json.dumps(
            {
                "directory": params.directory_path,
                "count": len(files),
                "entries": files[:100],  # Limit to 100 entries
                "truncated": len(files) > 100,
            },
            indent=2,
        )
