from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pytest

from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.chunks import (
    AudioChunk,
    ImageChunk,
    TextChunk,
    VideoChunk,
)
from rustic_ai.core.knowledgebase.knol_utils import KnolUtils


@pytest.fixture
def filesystem(tmp_path) -> FileSystem:
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )
    return fsr.resolve("test_guild", "test_agent")


@pytest.mark.asyncio
async def test_chunk_descriptor_write_read_list(filesystem: FileSystem):
    library = "library"
    knol_id = "knol_abc123"
    chunker = "default"

    filesystem.makedirs(f"{library}/{knol_id}", exist_ok=True)

    chunks = [
        TextChunk(
            id="t0",
            knol_id=knol_id,
            index=0,
            producer_id="test",
            encoding="utf-8",
            content_bytes=b"Hello",
            language="en",
        ),
        ImageChunk(id="i1", knol_id=knol_id, index=1, producer_id="test"),
        AudioChunk(id="a2", knol_id=knol_id, index=2, producer_id="test", start_ms=0, end_ms=1000),
        VideoChunk(id="v3", knol_id=knol_id, index=3, producer_id="test", start_ms=0, end_ms=500),
    ]

    for c in chunks:
        await KnolUtils.write_chunk_descriptor(filesystem, library, knol_id, chunker, c)

    # list descriptors
    listed = await KnolUtils.list_chunk_descriptors(filesystem, library, knol_id, chunker)
    assert len(listed) == 4
    # ensure order by index (lexicographically zero-padded)
    assert [c.index for c in listed] == [0, 1, 2, 3]
    # read one explicitly and check round-trip fields
    c2 = await KnolUtils.read_chunk_descriptor(filesystem, library, knol_id, chunker, 2)
    assert c2.kind == "audio"
    assert c2.knol_id == knol_id
    assert c2.index == 2


@pytest.mark.asyncio
async def test_derived_bytes_write_read_delete(filesystem: FileSystem):
    library = "library"
    knol_id = "knol_bytes"
    chunker = "default"
    filesystem.makedirs(f"{library}/{knol_id}", exist_ok=True)

    # Test for multiple modalities with default extensions
    modality_chunks = [
        TextChunk(id="t0", knol_id=knol_id, index=0, producer_id="test", encoding="utf-8", content_bytes=b"Hello"),
        ImageChunk(id="i1", knol_id=knol_id, index=1, producer_id="test"),
        AudioChunk(id="a2", knol_id=knol_id, index=2, producer_id="test", start_ms=0, end_ms=1000),
        VideoChunk(id="v3", knol_id=knol_id, index=3, producer_id="test", start_ms=0, end_ms=500),
    ]

    for c in modality_chunks:
        data = f"payload-{c.id}".encode("utf-8")
        await KnolUtils.write_chunk_derived_bytes(filesystem, library, chunker, c, data)

        # Confirm read round-trip
        read_back = await KnolUtils.read_chunk_derived_bytes(filesystem, library, chunker, c)
        assert read_back == data

        # Delete and ensure removal
        await KnolUtils.delete_chunk_derived_bytes(filesystem, library, chunker, c)
        ext = KnolUtils.default_bytes_ext_for_chunk(c)
        derived_path = KnolUtils._derived_bytes_path(library, knol_id, chunker, c.index, ext)
        assert (await filesystem._exists(derived_path)) is False


@pytest.mark.asyncio
async def test_preview_write_read_delete(filesystem: FileSystem):
    library = "library"
    knol_id = "knol_previews"
    chunker = "default"
    filesystem.makedirs(f"{library}/{knol_id}", exist_ok=True)

    # Use image and video which default to jpg previews
    modality_chunks = [
        ImageChunk(id="i1", knol_id=knol_id, index=1, producer_id="test"),
        VideoChunk(id="v3", knol_id=knol_id, index=3, producer_id="test", start_ms=0, end_ms=500),
    ]

    for c in modality_chunks:
        data = f"preview-{c.id}".encode("utf-8")
        await KnolUtils.write_chunk_preview(filesystem, library, chunker, c, data)

        read_back = await KnolUtils.read_chunk_preview(filesystem, library, chunker, c)
        assert read_back == data

        await KnolUtils.delete_chunk_preview(filesystem, library, chunker, c)
        ext = KnolUtils.default_preview_ext_for_chunk(c)
        preview_path = KnolUtils._preview_path(library, knol_id, chunker, c.index, ext)
        assert (await filesystem._exists(preview_path)) is False
