"""Test helpers for knowledge base tests."""

from typing import Optional

from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.constants import (
    CONTENT_FILENAME,
    DEFAULT_ENCODING,
    KNOL_META_FILENAME,
)
from rustic_ai.core.knowledgebase.model import Knol


async def write_test_knol(
    fs,
    library: str,
    knol: Knol,
    content_bytes: bytes,
) -> None:
    """Write a test knol to the filesystem."""
    knol_dir = f"{library}/{knol.id}"
    fs.makedirs(knol_dir, exist_ok=True)
    await fs._pipe_file(f"{knol_dir}/{CONTENT_FILENAME}", content_bytes)
    await fs._pipe_file(
        f"{knol_dir}/{KNOL_META_FILENAME}",
        knol.model_dump_json().encode(DEFAULT_ENCODING),
    )


def create_test_filesystem(tmp_path, org: str = "test_org", guild: str = "test_guild", agent: str = "test_agent"):
    """Create a test filesystem resolver."""
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )
    return fsr.resolve(org, guild, agent)


def create_test_knol(
    knol_id: str,
    name: str,
    mimetype: str,
    size_in_bytes: int = 0,
    language: Optional[str] = None,
    **kwargs,
) -> Knol:
    """Create a test knol with common defaults."""
    return Knol(
        id=knol_id,
        name=name,
        mimetype=mimetype,
        size_in_bytes=size_in_bytes,
        language=language,
        **kwargs,
    )
