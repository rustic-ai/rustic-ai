import io
import wave

import pytest

from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.chunkers import (
    AudioFixedByteChunker,
    AudioWavTimeChunker,
    ImageFixedByteChunker,
    ImageWholeFileChunker,
    VideoFixedByteChunker,
    VideoWholeFileChunker,
)
from rustic_ai.core.knowledgebase.knol_utils import KnolUtils
from rustic_ai.core.knowledgebase.model import Knol


async def _write_content(fs, library: str, knol: Knol, content: bytes) -> None:
    fs.makedirs(f"{library}/{knol.id}", exist_ok=True)
    await fs._pipe_file(f"{library}/{knol.id}/content", content)
    await fs._pipe_file(f"{library}/{knol.id}/.knol", knol.model_dump_json().encode("utf-8"))


@pytest.mark.asyncio
async def test_image_whole_and_bytes(tmp_path):
    fsr = FileSystemResolver(path_base=str(tmp_path), protocol="file", storage_options={}, asynchronous=True)
    fs = fsr.resolve("test_guild", "test_agent")
    library = "library"

    # Minimal fake image bytes (we don't decode)
    img_bytes = b"FAKEIMGDATA" * 100
    knol = Knol(id="img1", name="img.jpg", mimetype="image/jpeg", size_in_bytes=len(img_bytes))
    await _write_content(fs, library, knol, img_bytes)
    kn = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    whole = ImageWholeFileChunker(id="img-whole")
    chunks = [c async for c in whole.split(kn, fs=fs, library_path=library)]
    assert len(chunks) == 1
    assert chunks[0].mimetype == "image/jpeg"

    byter = ImageFixedByteChunker(id="img-bytes", chunk_bytes=64)
    parts = [c async for c in byter.split(kn, fs=fs, library_path=library)]
    assert len(parts) >= 1
    # Verify derived bytes round-trip
    first_payload = await KnolUtils.read_chunk_derived_bytes(fs, library, byter.id, parts[0])
    assert isinstance(first_payload, (bytes, bytearray)) and len(first_payload) > 0

    # Modality guard: non-image should yield zero
    other = Knol(id="imgX", name="a.bin", mimetype="application/octet-stream", size_in_bytes=10)
    await _write_content(fs, library, other, b"0123456789")
    other_kn = await KnolUtils.read_knol_from_library(fs, library, other.id)
    assert [c async for c in whole.split(other_kn, fs=fs, library_path=library)] == []
    assert [c async for c in byter.split(other_kn, fs=fs, library_path=library)] == []

    # Boundary sizes for byte chunker
    small_kn = Knol(id="img2", name="small.jpg", mimetype="image/jpeg", size_in_bytes=5)
    await _write_content(fs, library, small_kn, b"abcde")
    small = await KnolUtils.read_knol_from_library(fs, library, small_kn.id)
    byter2 = ImageFixedByteChunker(id="img-bytes-2", chunk_bytes=10)
    small_parts = [c async for c in byter2.split(small, fs=fs, library_path=library)]
    assert len(small_parts) == 1
    p = await KnolUtils.read_chunk_derived_bytes(fs, library, byter2.id, small_parts[0])
    assert p == b"abcde"

    exact_kn = Knol(id="img3", name="exact.jpg", mimetype="image/jpeg", size_in_bytes=6)
    await _write_content(fs, library, exact_kn, b"abcdef")
    exact = await KnolUtils.read_knol_from_library(fs, library, exact_kn.id)
    byter3 = ImageFixedByteChunker(id="img-bytes-3", chunk_bytes=3)
    exact_parts = [c async for c in byter3.split(exact, fs=fs, library_path=library)]
    assert len(exact_parts) == 2
    p0 = await KnolUtils.read_chunk_derived_bytes(fs, library, byter3.id, exact_parts[0])
    p1 = await KnolUtils.read_chunk_derived_bytes(fs, library, byter3.id, exact_parts[1])
    assert p0 == b"abc" and p1 == b"def"

    # Delete derived bytes
    await KnolUtils.delete_chunk_derived_bytes(fs, library, byter3.id, exact_parts[0])
    # Not asserting exists check; just ensure no exception


@pytest.mark.asyncio
async def test_audio_byte_and_wav_time(tmp_path):
    fsr = FileSystemResolver(path_base=str(tmp_path), protocol="file", storage_options={}, asynchronous=True)
    fs = fsr.resolve("test_guild", "test_agent")
    library = "library"

    # Create a tiny in-memory WAV: 1 channel, 8kHz, 1s of silence
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 8000)
    wav_bytes = buf.getvalue()

    wav_knol = Knol(id="aud1", name="tone.wav", mimetype="audio/wav", size_in_bytes=len(wav_bytes))
    await _write_content(fs, library, wav_knol, wav_bytes)
    wav = await KnolUtils.read_knol_from_library(fs, library, wav_knol.id)

    # Byte chunker works on any audio
    abyte = AudioFixedByteChunker(id="aud-bytes", chunk_bytes=256)
    a_parts = [c async for c in abyte.split(wav, fs=fs, library_path=library)]
    assert len(a_parts) >= 1
    payload = await KnolUtils.read_chunk_derived_bytes(fs, library, abyte.id, a_parts[0])
    assert isinstance(payload, (bytes, bytearray)) and len(payload) > 0

    # WAV time chunker produces valid WAV segments with timing metadata
    atime = AudioWavTimeChunker(id="aud-wav-time", chunk_ms=200, overlap_ms=50)
    segs = [c async for c in atime.split(wav, fs=fs, library_path=library)]
    assert len(segs) >= 3  # due to overlap
    assert segs[0].start_ms == 0
    assert segs[0].sample_rate_hz == 8000 and segs[0].channels == 1
    seg_payload = await KnolUtils.read_chunk_derived_bytes(fs, library, atime.id, segs[0], ext="wav")
    # Validate first segment is a WAV by opening
    with wave.open(io.BytesIO(seg_payload), "rb") as wf:
        assert wf.getframerate() == 8000 and wf.getnchannels() == 1

    # Guards
    not_wav = Knol(id="aud2", name="a.mp3", mimetype="audio/mpeg", size_in_bytes=10)
    await _write_content(fs, library, not_wav, b"xx" * 5)
    not_wav_kn = await KnolUtils.read_knol_from_library(fs, library, not_wav.id)
    assert [c async for c in atime.split(not_wav_kn, fs=fs, library_path=library)] == []

    # Boundary: very short wav (< chunk)
    buf2 = io.BytesIO()
    with wave.open(buf2, "wb") as wf2:
        wf2.setnchannels(1)
        wf2.setsampwidth(2)
        wf2.setframerate(8000)
        wf2.writeframes(b"\x00\x00" * 1000)  # 125ms
    short_wav = Knol(id="aud3", name="short.wav", mimetype="audio/wav", size_in_bytes=len(buf2.getvalue()))
    await _write_content(fs, library, short_wav, buf2.getvalue())
    short_kn = await KnolUtils.read_knol_from_library(fs, library, short_wav.id)
    segs_short = [
        c
        async for c in AudioWavTimeChunker(id="aud-wav-time-2", chunk_ms=500).split(
            short_kn, fs=fs, library_path=library
        )
    ]
    assert len(segs_short) == 1

    # Overlap >= chunk_ms clamps
    segs_clamp = [
        c
        async for c in AudioWavTimeChunker(id="aud-wav-time-3", chunk_ms=200, overlap_ms=500).split(
            wav, fs=fs, library_path=library
        )
    ]
    assert len(segs_clamp) >= 1


@pytest.mark.asyncio
async def test_video_whole_and_bytes(tmp_path):
    fsr = FileSystemResolver(path_base=str(tmp_path), protocol="file", storage_options={}, asynchronous=True)
    fs = fsr.resolve("test_guild", "test_agent")
    library = "library"

    # Minimal fake video bytes (we don't decode)
    vid_bytes = b"FAKEVIDDATA" * 100
    knol = Knol(id="vid1", name="vid.mp4", mimetype="video/mp4", size_in_bytes=len(vid_bytes))
    await _write_content(fs, library, knol, vid_bytes)
    kn = await KnolUtils.read_knol_from_library(fs, library, knol.id)

    whole = VideoWholeFileChunker(id="vid-whole")
    chunks = [c async for c in whole.split(kn, fs=fs, library_path=library)]
    assert len(chunks) == 1
    assert chunks[0].mimetype == "video/mp4"

    byter = VideoFixedByteChunker(id="vid-bytes", chunk_bytes=64)
    parts = [c async for c in byter.split(kn, fs=fs, library_path=library)]
    assert len(parts) >= 1
    first_payload = await KnolUtils.read_chunk_derived_bytes(fs, library, byter.id, parts[0])
    assert isinstance(first_payload, (bytes, bytearray)) and len(first_payload) > 0

    # Guards
    other = Knol(id="vidX", name="a.bin", mimetype="application/octet-stream", size_in_bytes=10)
    await _write_content(fs, library, other, b"0123456789")
    other_kn = await KnolUtils.read_knol_from_library(fs, library, other.id)
    assert [c async for c in whole.split(other_kn, fs=fs, library_path=library)] == []
    assert [c async for c in byter.split(other_kn, fs=fs, library_path=library)] == []

    # Boundary: small/ exact multiple
    small_kn = Knol(id="vid2", name="small.mp4", mimetype="video/mp4", size_in_bytes=5)
    await _write_content(fs, library, small_kn, b"abcde")
    small = await KnolUtils.read_knol_from_library(fs, library, small_kn.id)
    byter2 = VideoFixedByteChunker(id="vid-bytes-2", chunk_bytes=10)
    small_parts = [c async for c in byter2.split(small, fs=fs, library_path=library)]
    assert len(small_parts) == 1
    exact_kn = Knol(id="vid3", name="exact.mp4", mimetype="video/mp4", size_in_bytes=6)
    await _write_content(fs, library, exact_kn, b"abcdef")
    exact = await KnolUtils.read_knol_from_library(fs, library, exact_kn.id)
    byter3 = VideoFixedByteChunker(id="vid-bytes-3", chunk_bytes=3)
    exact_parts = [c async for c in byter3.split(exact, fs=fs, library_path=library)]
    assert len(exact_parts) == 2

    # Custom library path works
    custom_lib = "lib_custom"
    fs.makedirs(custom_lib, exist_ok=True)
    knol2 = Knol(id="vid4", name="c.mp4", mimetype="video/mp4", size_in_bytes=len(vid_bytes))
    await _write_content(fs, custom_lib, knol2, vid_bytes)
    kn2 = await KnolUtils.read_knol_from_library(fs, custom_lib, knol2.id)
    parts2 = [c async for c in byter.split(kn2, fs=fs, library_path=custom_lib)]
    assert len(parts2) >= 1
