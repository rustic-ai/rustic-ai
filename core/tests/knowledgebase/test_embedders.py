import pytest

from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.embedders import (
    AudioMetaStatsEmbedder,
    ByteHistogramTextEmbedder,
    ByteNgramTextEmbedder,
    ContentDigestEmbedder,
    FeatureHashingTextEmbedder,
)


def _unit_norm(vec):
    s = sum(float(x) * float(x) for x in vec) ** 0.5
    return abs(s - 1.0) < 1e-6 or s == 0.0


@pytest.mark.asyncio
async def test_feature_hashing_text_embedder_basic():
    emb = FeatureHashingTextEmbedder(id="feathash", dimension=128, normalize=True)
    chunk = TextChunk(
        id="t1",
        knol_id="k1",
        index=0,
        producer_id="test",
        encoding="utf-8",
        content_bytes=b"Hello world hello",
    )
    v1 = await emb.embed(chunk, fs=None, library_path="library")
    # Base applies normalization and validation in embed_many/seq; here we call helper
    v1 = emb._validate_and_optionally_normalize(v1)
    assert len(v1) == 128
    assert _unit_norm(v1)
    # Deterministic
    v2 = emb._validate_and_optionally_normalize(await emb.embed(chunk, fs=None, library_path="library"))
    assert v1 == v2
    # supports_mimetype
    assert emb.supports_mimetype("text/plain")
    assert emb.supports_mimetype("application/json")
    assert not emb.supports_mimetype("image/png")
    # embed_many preserves order and normalizes
    c2 = TextChunk(id="t2", knol_id="k1", index=1, producer_id="test", encoding="utf-8", content_bytes=b"world hello")
    many = await emb.embed_many([chunk, c2], fs=None, library_path="library")
    assert len(many) == 2 and many[0] != many[1]
    assert all(abs(sum(x * x for x in v) ** 0.5 - 1.0) < 1e-6 or sum(v) == 0.0 for v in many)


@pytest.mark.asyncio
async def test_embed_seq_streaming_and_normalization():
    emb = FeatureHashingTextEmbedder(id="feathash2", dimension=64, normalize=True)

    async def _aiter():
        yield TextChunk(id="s1", knol_id="k1", index=0, producer_id="test", encoding="utf-8", content_bytes=b"first")
        yield TextChunk(id="s2", knol_id="k1", index=1, producer_id="test", encoding="utf-8", content_bytes=b"second")
        yield TextChunk(id="s3", knol_id="k1", index=2, producer_id="test", encoding="utf-8", content_bytes=b"third")

    results = [v async for v in emb.embed_seq(_aiter(), fs=None, library_path="library")]
    assert len(results) == 3
    for v in results:
        n = sum(x * x for x in v) ** 0.5
        assert abs(n - 1.0) < 1e-6 or sum(v) == 0.0


@pytest.mark.asyncio
async def test_byte_histogram_text_embedder():
    emb = ByteHistogramTextEmbedder(id="bytehist")
    chunk = TextChunk(id="t1", knol_id="k1", index=0, producer_id="test", encoding="utf-8", content_bytes=b"abc")
    v = emb._validate_and_optionally_normalize(await emb.embed(chunk, fs=None, library_path="library"))
    assert len(v) == 256
    assert _unit_norm(v) or sum(v) == 0.0
    # Wrong chunk type raises
    from rustic_ai.core.knowledgebase.chunks import AudioChunk

    with pytest.raises(TypeError):
        await emb.embed(AudioChunk(id="a1", knol_id="k1", index=0, producer_id="test"), fs=None, library_path="library")

    # Non-ASCII encoding handling
    chunk2 = TextChunk(
        id="t2", knol_id="k1", index=1, producer_id="test", content_bytes="café".encode("latin-1"), encoding="latin-1"
    )
    v2 = emb._validate_and_optionally_normalize(await emb.embed(chunk2, fs=None, library_path="library"))
    assert len(v2) == 256
    assert _unit_norm(v2) or sum(v2) == 0.0


@pytest.mark.asyncio
async def test_content_digest_embedder():
    emb = ContentDigestEmbedder(id="digest", dimension=32)
    c1 = TextChunk(id="t1", knol_id="k1", index=0, producer_id="test", encoding="utf-8", content_bytes=b"same")
    c2 = TextChunk(id="t2", knol_id="k1", index=1, producer_id="test", encoding="utf-8", content_bytes=b"same")
    v1 = emb._validate_and_optionally_normalize(await emb.embed(c1, fs=None, library_path="library"))
    v2 = emb._validate_and_optionally_normalize(await emb.embed(c2, fs=None, library_path="library"))
    assert len(v1) == 32
    assert v1 == v2  # determinism for same content
    # Sensitivity to changes
    c3 = TextChunk(id="t3", knol_id="k1", index=2, producer_id="test", encoding="utf-8", content_bytes=b"different")
    v3 = emb._validate_and_optionally_normalize(await emb.embed(c3, fs=None, library_path="library"))
    assert v1 != v3

    # get_dimension
    assert emb.get_dimension() == 32


@pytest.mark.asyncio
async def test_byte_ngram_text_embedder():
    emb = ByteNgramTextEmbedder(id="ngram", dimension=256, ngram_k=3)
    chunk = TextChunk(id="t1", knol_id="k1", index=0, producer_id="test", encoding="utf-8", content_bytes=b"abcdef")
    v = emb._validate_and_optionally_normalize(await emb.embed(chunk, fs=None, library_path="library"))
    assert len(v) == 256
    assert _unit_norm(v) or sum(v) == 0.0
    # Ngram longer than text -> zero
    emb2 = ByteNgramTextEmbedder(id="ngram2", dimension=64, ngram_k=10)
    v2 = emb2._validate_and_optionally_normalize(
        await emb2.embed(
            TextChunk(id="t2", knol_id="k1", index=1, producer_id="test", encoding="utf-8", content_bytes=b"abc"),
            fs=None,
            library_path="library",
        )
    )
    assert sum(v2) == 0.0


@pytest.mark.asyncio
async def test_dimension_mismatch_guard_in_embed_many():
    from rustic_ai.core.knowledgebase.plugins import EmbedderPlugin

    class BadEmbedder(EmbedderPlugin):
        dimension: int = 8

        async def embed(self, chunk, *, fs, library_path: str = "library"):  # returns wrong length
            return [0.0] * 5

    bad = BadEmbedder(id="bad")
    with pytest.raises(ValueError):
        await bad.embed_many(
            [TextChunk(id="x", knol_id="k", index=0, producer_id="test", encoding="utf-8", content_bytes=b"t")],
            fs=None,
            library_path="library",
        )


@pytest.mark.asyncio
async def test_audio_meta_stats_embedder():
    emb = AudioMetaStatsEmbedder(id="audio-stats", dimension=8)
    from rustic_ai.core.knowledgebase.chunks import AudioChunk

    ch = AudioChunk(
        id="a1",
        knol_id="k1",
        index=0,
        producer_id="test",
        start_ms=0,
        end_ms=1000,
        sample_rate_hz=8000,
        channels=1,
        mimetype="audio/wav",
    )
    v = emb._validate_and_optionally_normalize(await emb.embed(ch, fs=None, library_path="library"))
    assert len(v) == 8
    assert _unit_norm(v) or sum(v) == 0.0
    # Multi-channel and scaling clamps
    ch2 = AudioChunk(
        id="a2",
        knol_id="k1",
        index=1,
        producer_id="test",
        start_ms=0,
        end_ms=1_000_000,
        sample_rate_hz=96_000,
        channels=2,
        mimetype="audio/wav",
    )
    v2 = emb._validate_and_optionally_normalize(await emb.embed(ch2, fs=None, library_path="library"))
    assert len(v2) == 8
    # supports_mimetype
    assert emb.supports_mimetype("audio/wav")
    assert not emb.supports_mimetype("text/plain")
