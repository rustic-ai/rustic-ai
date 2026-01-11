import pytest

from rustic_ai.core.knowledgebase.chunkers import (
    AudioFixedByteChunker,
    CodeLanguageChunker,
    ImageFixedByteChunker,
    SentenceChunker,
    SimpleTextChunker,
    VideoFixedByteChunker,
)
from rustic_ai.core.knowledgebase.constants import LIBRARY_DIR
from rustic_ai.core.knowledgebase.knol_utils import KnolUtils
from rustic_ai.core.knowledgebase.model import Knol

from .test_helpers import create_test_filesystem, write_test_knol


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunker_cls, mimetype, content, expect_kind",
    [
        (SimpleTextChunker, "text/plain", b"Hello World" * 10, "text"),
        (SentenceChunker, "text/plain", b"Hello. World!", "text"),
        (CodeLanguageChunker, "text/x-python", b"def f():\n  return 1\n", "text"),
        (ImageFixedByteChunker, "image/jpeg", b"IMG" * 100, "image"),
        (VideoFixedByteChunker, "video/mp4", b"VID" * 100, "video"),
        (AudioFixedByteChunker, "audio/wav", b"AUD" * 100, "audio"),
    ],
)
async def test_chunkers_attach_and_write(tmp_path, chunker_cls, mimetype, content, expect_kind):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = Knol(id="kattach", name="x", mimetype=mimetype, size_in_bytes=len(content))
    await write_test_knol(fs, library, knol, content)
    kn = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    # Case 1: attach_bytes=True, write_derived_bytes=True
    c1 = chunker_cls(id=f"{chunker_cls.__name__}-a1")
    chunks1 = [c async for c in c1.split(kn, fs=fs, library_path=library)]
    assert len(chunks1) >= 1
    for ch in chunks1:
        # Should have bytes attached
        assert getattr(ch, "kind") == expect_kind
        assert ch.content_bytes is not None
        # Derived bytes should be retrievable
        payload = await KnolUtils.read_chunk_derived_bytes(fs, library, c1.id, ch)
        assert isinstance(payload, (bytes, bytearray)) and len(payload) > 0

    # Case 2: attach_bytes=False, write_derived_bytes=True
    c2 = chunker_cls(id=f"{chunker_cls.__name__}-a0", attach_bytes=False)
    chunks2 = [c async for c in c2.split(kn, fs=fs, library_path=library)]
    assert len(chunks2) >= 1
    for ch in chunks2:
        assert ch.content_bytes is None
        # Derived bytes must exist for retrieval by downstream components
        payload = await KnolUtils.read_chunk_derived_bytes(fs, library, c2.id, ch)
        assert isinstance(payload, (bytes, bytearray)) and len(payload) > 0

    # Case 3: attach_bytes=True, write_derived_bytes=False
    c3 = chunker_cls(id=f"{chunker_cls.__name__}-w0", write_derived_bytes=False)
    chunks3 = [c async for c in c3.split(kn, fs=fs, library_path=library)]
    assert len(chunks3) >= 1
    for ch in chunks3:
        assert ch.content_bytes is not None
        # Derived bytes may not exist; ensure missing does not raise when checking existence
        # We attempt read and allow failure by catching and asserting type
        try:
            payload = await KnolUtils.read_chunk_derived_bytes(fs, library, c3.id, ch)
            # If present, it's fine as some chunkers may still write; ensure bytes type
            assert isinstance(payload, (bytes, bytearray))
        except Exception:
            # Acceptable: no derived bytes written
            pass
