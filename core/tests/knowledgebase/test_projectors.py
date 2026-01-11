import pytest

from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.projectors import (
    HTMLToTextProjector,
    JSONToTextProjector,
    TextNormalizeWhitespaceProjector,
)


@pytest.mark.asyncio
async def test_html_to_text_basic():
    projector = HTMLToTextProjector(id="html2text")
    html = b"<html><head><title>T</title><style>.x{}</style></head><body><h1>Hi</h1><p>A<br>B</p><script>var x=1</script></body></html>"
    chunk = TextChunk(
        id="c1",
        knol_id="k1",
        index=0,
        producer_id="test",
        content_bytes=html,
        encoding="utf-8",
        mimetype="text/html",
    )
    out = await projector.project(chunk, fs=None, library_path="library")
    assert isinstance(out, TextChunk)
    assert out.mimetype == "text/plain"
    t = out.text
    assert "Hi" in t and "A" in t and "B" in t
    assert "var x" not in t  # script removed


@pytest.mark.asyncio
async def test_json_to_text_basic():
    projector = JSONToTextProjector(id="json2text", indent=2)
    data = b'{\n  "a": 1, "b": [2,3]\n}'
    chunk = TextChunk(
        id="c2",
        knol_id="k1",
        index=1,
        producer_id="test",
        content_bytes=data,
        encoding="utf-8",
        mimetype="application/json",
    )
    out = await projector.project(chunk, fs=None, library_path="library")
    assert isinstance(out, TextChunk)
    assert out.mimetype == "text/plain"
    assert "\n" in out.text and '"a": 1' in out.text


@pytest.mark.asyncio
async def test_text_normalize_whitespace():
    projector = TextNormalizeWhitespaceProjector(id="norm")
    txt = b"Line 1\t  Line 2\n\n\nLine   3  "
    chunk = TextChunk(
        id="c3",
        knol_id="k1",
        index=2,
        producer_id="test",
        content_bytes=txt,
        encoding="utf-8",
        mimetype="text/plain",
    )
    out = await projector.project(chunk, fs=None, library_path="library")
    assert isinstance(out, TextChunk)
    t = out.text
    # Collapses tabs/spaces, trims, reduces blank lines
    assert t.startswith("Line 1 ")
    assert t.endswith("Line 3")
    assert "\n\n\n" not in t
