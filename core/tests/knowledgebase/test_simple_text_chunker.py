import pytest

from rustic_ai.core.knowledgebase.chunkers.simple_text import SimpleTextChunker
from rustic_ai.core.knowledgebase.constants import DEFAULT_ENCODING, LIBRARY_DIR
from rustic_ai.core.knowledgebase.knol_utils import KnolUtils
from rustic_ai.core.knowledgebase.metadata import ExtraMetaPart

from .test_helpers import create_test_filesystem, create_test_knol, write_test_knol


@pytest.mark.asyncio
async def test_simple_text_chunker_single_chunk(tmp_path):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k1", "doc.txt", "text/plain")

    text = "hello world"
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple", chunk_size=100, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == text
    assert chunks[0].mimetype == "text/plain"


def _expected_slices(text: str, size: int, overlap: int):
    pieces = []
    i = 0
    n = len(text)
    while i + size <= n:
        pieces.append(text[i : i + size])
        i += size - overlap
    if i < n:
        pieces.append(text[i:])
    return pieces


@pytest.mark.asyncio
async def test_simple_text_chunker_overlap(tmp_path):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k2", "doc.txt", "text/plain")

    text = "0123456789" * 3  # 30 chars
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    size, overlap = 10, 3
    chunker = SimpleTextChunker(id="simple2", chunk_size=size, chunk_overlap=overlap)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    expected = _expected_slices(text, size, overlap)
    assert [c.text for c in chunks] == expected
    assert [c.index for c in chunks] == list(range(len(expected)))


@pytest.mark.asyncio
async def test_simple_text_chunker_non_text_mimetype(tmp_path):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k3", name="img.png", mimetype="image/png", size_in_bytes=0)
    await write_test_knol(fs, library, knol, b"\x89PNG\r\n")
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple3", chunk_size=10, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]
    assert chunks == []


@pytest.mark.asyncio
async def test_simple_text_chunker_respects_encoding(tmp_path):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR

    # Put encoding in metaparts (ExtraMetaPart) so metadata_consolidated carries it
    knol = create_test_knol(
        "k4",
        "cafe.txt",
        "text/plain",
        metaparts=[ExtraMetaPart(kind="extra", data={"encoding": "latin-1"})],
    )
    text = "café à la carte"
    await write_test_knol(fs, library, knol, text.encode("latin-1"))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple4", chunk_size=100, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].encoding == "latin-1"


@pytest.mark.asyncio
async def test_simple_text_chunker_empty_text(tmp_path):
    """Test chunker with empty text."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k5", "empty.txt", "text/plain")

    await write_test_knol(fs, library, knol, b"")
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple5", chunk_size=10, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) == 0  # Empty text should produce no chunks


@pytest.mark.asyncio
async def test_simple_text_chunker_single_character(tmp_path):
    """Test chunker with single character."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k6", "single.txt", "text/plain")

    text = "a"
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple6", chunk_size=10, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) == 1
    assert chunks[0].text == text


@pytest.mark.asyncio
async def test_simple_text_chunker_chunk_size_one(tmp_path):
    """Test chunker with chunk_size=1."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k7", "chars.txt", "text/plain")

    text = "abc"
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple6a", chunk_size=1, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) == 3
    assert [c.text for c in chunks] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_simple_text_chunker_overlap_ge_chunk_size(tmp_path):
    """Test chunker with overlap >= chunk_size (should be clamped)."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k8", "overlap.txt", "text/plain")

    text = "0123456789"  # 10 chars
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    # overlap = chunk_size should be clamped to chunk_size - 1
    chunker = SimpleTextChunker(id="simple7", chunk_size=5, chunk_overlap=5)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    # With overlap=5 and chunk_size=5, overlap gets clamped to 4
    # Should produce 6 chunks: "01234", "12345", "23456", "34567", "45678", "56789"
    assert len(chunks) == 6
    assert chunks[0].text == "01234"
    assert chunks[1].text == "12345"  # 4 chars overlap
    assert chunks[2].text == "23456"
    assert chunks[3].text == "34567"
    assert chunks[4].text == "45678"
    assert chunks[5].text == "56789"


@pytest.mark.asyncio
async def test_simple_text_chunker_streaming_large_file(tmp_path):
    """Test chunker with large file that requires streaming."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k9", "large.txt", "text/plain")

    # Create a large text file (10KB)
    text = "Hello world! " * 1000  # ~13KB
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple8", chunk_size=1000, chunk_overlap=100)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    assert len(chunks) > 10  # Should produce multiple chunks
    # Verify chunks are properly sized
    for chunk in chunks[:-1]:  # All except last chunk
        assert len(chunk.text) == 1000
    # Verify overlap
    assert chunks[1].text.startswith(chunks[0].text[-100:])
    # Verify we got most of the content (allowing for streaming differences)
    total_length = sum(len(ch.text) for ch in chunks)
    assert total_length >= len(text) * 0.95  # At least 95% of original content


@pytest.mark.asyncio
async def test_simple_text_chunker_chunk_ids_unique(tmp_path):
    """Test that chunk IDs are unique and follow expected pattern."""
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = create_test_knol("k10", "ids.txt", "text/plain")

    text = "0123456789" * 5  # 50 chars
    await write_test_knol(fs, library, knol, text.encode(DEFAULT_ENCODING))
    knol_loaded = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    chunker = SimpleTextChunker(id="simple9", chunk_size=10, chunk_overlap=0)
    chunks = [c async for c in chunker.split(knol_loaded, fs=fs, library_path=library)]

    # Verify unique IDs
    chunk_ids = [c.id for c in chunks]
    assert len(set(chunk_ids)) == len(chunk_ids)

    # Verify ID pattern
    for i, chunk in enumerate(chunks):
        expected_id = f"{knol.id}:SimpleTextChunker:{i}"
        assert chunk.id == expected_id
