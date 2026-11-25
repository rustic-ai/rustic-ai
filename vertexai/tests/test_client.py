"""GenAI clients keep explicit Vertex configuration without legacy SDK globals."""

from unittest.mock import patch

from rustic_ai.vertexai.client import VertexAIBase


def test_vertex_client_uses_explicit_project_and_location():
    with patch("rustic_ai.vertexai.client.genai.Client", side_effect=[object(), object()]) as client:
        first = VertexAIBase(project_id="project-one", location="us-central1")
        second = VertexAIBase(project_id="project-two", location="europe-west1")

    assert client.call_count == 2
    assert first.genai_client is not second.genai_client
    for call, project, location in zip(
        client.call_args_list, ("project-one", "project-two"), ("us-central1", "europe-west1")
    ):
        assert call.kwargs["vertexai"] is True
        assert call.kwargs["project"] == project
        assert call.kwargs["location"] == location
        assert call.kwargs["http_options"].api_version == "v1"


def test_vertex_client_resolves_environment_defaults(monkeypatch):
    monkeypatch.setenv("VERTEXAI_PROJECT", "environment-project")
    monkeypatch.setenv("VERTEXAI_LOCATION", "asia-east1")
    with patch("rustic_ai.vertexai.client.genai.Client") as client:
        VertexAIBase()
    assert client.call_args.kwargs["project"] == "environment-project"
    assert client.call_args.kwargs["location"] == "asia-east1"
