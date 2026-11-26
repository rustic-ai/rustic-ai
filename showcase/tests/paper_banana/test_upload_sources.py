"""Local HTTP upload acquisition through the shipped PaperBanana routes."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

import pytest
import test_paper_banana
from test_paper_banana import instance, result, send

from rustic_ai.showcase.paper_banana_sources import HttpUploadSourceReader, source_uri

launch = test_paper_banana.launch


@pytest.fixture
def server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        redirect = "/reference.md"

        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("X-Upload-Token")))
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", self.redirect)
                self.end_headers()
                return
            if self.path.startswith("/slow"):
                time.sleep(0.35)
            body = b"x" * 100000 if self.path.startswith("/large") else b"Harbor project budget is CAD 42000."
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="Original-Harbor.md"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=service.serve_forever)
    worker.start()
    origin = f"http://127.0.0.1:{service.server_port}"
    yield origin, calls, Handler
    service.shutdown()
    worker.join(3)
    service.server_close()


def request(url, text=None):
    parts = [{"type": "file_url", "file_url": {"url": url}}]
    if text:
        parts.append({"type": "text", "text": text})
    return {"messages": [{"role": "user", "content": parts}]}


@pytest.mark.parametrize("native", [False, True])
def test_http_upload_preserves_metadata_and_removes_signed_query(launch, server, native):
    origin, _, _ = server
    guild, _, memory, caller, _, llms, _ = launch(origins=[origin], native=native)
    send(caller, request(origin + "/reference.md?token=private", "Illustrate Harbor budget"))
    assert result(caller).process_status == "completed"
    outcomes = [
        message
        for message in instance(guild, "trace_probe").get_messages()
        if message.format.endswith("PaperBananaResult")
    ]
    assert len(outcomes) == 1
    source = outcomes[0].payload["sources"][0]
    assert source["name"] == "Original-Harbor.md" and source["mime_type"] == "text/markdown"
    assert source["source_uri"] == origin + "/reference.md"
    prompt = llms["planner_agent"].calls[-1].messages[-1].content
    assert "private" not in prompt and "42000" in prompt
    assert "token=" not in str(outcomes[0].session_state)


def test_unconfigured_origin_fails_without_fetching(launch, server):
    origin, calls, _ = server
    _, _, memory, caller, _, _, _ = launch()
    send(caller, request(origin + "/reference.md"))
    assert result(caller).process_status == "error"
    assert not calls and not memory.ingestions


def test_redirects_revalidate_origins_and_preserve_same_origin_credentials(server):
    origin, calls, handler = server
    reader = HttpUploadSourceReader([origin], {"X-Upload-Token": "private"})
    upload = asyncio.run(reader.read(origin + "/redirect", 1000, time.monotonic() + 2))
    assert b"42000" in upload.data
    assert calls == [("/redirect", "private"), ("/reference.md", "private")]
    handler.redirect = "http://127.0.0.1:1/not-permitted"
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(reader.read(origin + "/redirect", 1000, time.monotonic() + 2))
    assert len(calls) == 3


def test_streaming_byte_bound_and_workflow_timeout(launch, server):
    origin, _, _ = server
    _, _, memory, caller, _, _, _ = launch(origins=[origin], max_source_bytes=16, max_workflow_bytes=16)
    send(caller, request(origin + "/large"))
    assert result(caller).process_status == "error" and not memory.ingestions
    _, coord, memory, caller, _, _, _ = launch(origins=[origin], deadline_seconds=0.08)
    publisher = threading.Thread(target=send, args=(caller, request(origin + "/slow")))
    publisher.start()
    try:
        assert "Workflow timed out" in result(caller, 0.3).payload["text"]
        publisher.join(2)
        time.sleep(0.4)
        assert not coord._requests and not memory.ingestions and not caller.get_messages()
    finally:
        publisher.join(2)


def test_allowed_cross_origin_redirect_drops_configured_credentials(server):
    origin, calls, handler = server
    other_origin = origin.replace("127.0.0.1", "localhost")
    handler.redirect = other_origin + "/reference.md"
    reader = HttpUploadSourceReader([origin, other_origin], {"X-Upload-Token": "private"})
    assert asyncio.run(reader.read(origin + "/redirect", 1000, time.monotonic() + 2)).data
    assert calls == [("/redirect", "private"), ("/reference.md", None)]
    assert source_uri("https://user:password@example.org/file?token=private#secret") == "https://example.org/file"
