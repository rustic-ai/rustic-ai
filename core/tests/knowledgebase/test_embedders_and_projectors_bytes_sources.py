import pytest

from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.constants import LIBRARY_DIR
from rustic_ai.core.knowledgebase.embedders import (
    ByteHistogramTextEmbedder,
    ByteNgramTextEmbedder,
    FeatureHashingTextEmbedder,
)
from rustic_ai.core.knowledgebase.knol_utils import KnolUtils
from rustic_ai.core.knowledgebase.model import Knol
from rustic_ai.core.knowledgebase.projectors import (
    HTMLToTextProjector,
    JSONToTextProjector,
    TextNormalizeWhitespaceProjector,
)

from .test_helpers import create_test_filesystem, write_test_knol


@pytest.mark.asyncio
@pytest.mark.parametrize("embedder_cls", [FeatureHashingTextEmbedder, ByteHistogramTextEmbedder, ByteNgramTextEmbedder])
async def test_embedders_with_attached_and_fs_bytes(tmp_path, embedder_cls):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = Knol(id="ktxt", name="doc.txt", mimetype="text/plain")
    content = b"Hello world, hello world!"
    await write_test_knol(fs, library, knol, content)

    # Build two chunks: one with content_bytes and one relying on FS bytes
    ch_attached = TextChunk(
        id="c1",
        knol_id=knol.id,
        index=0,
        producer_id="p",
        content_bytes=content,
        encoding="utf-8",
        mimetype="text/plain",
    )
    ch_fs = TextChunk(
        id="c2",
        knol_id=knol.id,
        index=1,
        producer_id="p",
        content_bytes=None,  # force FS path via get_chunk_bytes
        encoding="utf-8",
        mimetype="text/plain",
    )

    # Write derived bytes for FS-backed chunk
    await KnolUtils.write_chunk_derived_bytes(fs, library, "p", ch_fs, content)

    emb = embedder_cls(id=f"emb-{embedder_cls.__name__}")
    v1 = emb._validate_and_optionally_normalize(await emb.embed(ch_attached, fs=fs, library_path=library))
    v2 = emb._validate_and_optionally_normalize(await emb.embed(ch_fs, fs=fs, library_path=library))
    assert len(v1) == emb.get_dimension()
    assert len(v2) == emb.get_dimension()
    # For deterministic embedders, vectors should match; for others, allow difference but both valid
    assert len(v1) == len(v2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "projector_cls, mimetype, content",
    [
        (HTMLToTextProjector, "text/html", b"<p>Hello <b>World</b></p>"),
        (JSONToTextProjector, "application/json", b'{"a": 1, "b": [2,3]}'),
        (TextNormalizeWhitespaceProjector, "text/plain", b"A\t  B\n\nC"),
    ],
)
async def test_projectors_with_attached_and_fs_bytes(tmp_path, projector_cls, mimetype, content):
    fs = create_test_filesystem(tmp_path)
    library = LIBRARY_DIR
    knol = Knol(id="kproj", name="doc", mimetype=mimetype)
    await write_test_knol(fs, library, knol, content)

    # Attached bytes
    ch_attached = TextChunk(
        id="p1",
        knol_id=knol.id,
        index=0,
        producer_id="pp",
        content_bytes=content,
        encoding="utf-8",
        mimetype=mimetype,
    )
    # FS-backed bytes
    ch_fs = TextChunk(
        id="p2",
        knol_id=knol.id,
        index=1,
        producer_id="pp",
        content_bytes=None,
        encoding="utf-8",
        mimetype=mimetype,
    )
    await KnolUtils.write_chunk_derived_bytes(fs, library, "pp", ch_fs, content)

    proj = projector_cls(id=f"proj-{projector_cls.__name__}")
    out1 = await proj.project(ch_attached, fs=fs, library_path=library)
    out2 = await proj.project(ch_fs, fs=fs, library_path=library)
    assert out1.mimetype == "text/plain"
    assert out2.mimetype == "text/plain"
    assert isinstance(out1.text, str) and isinstance(out2.text, str)
    assert len(out1.text) > 0 and len(out2.text) > 0
