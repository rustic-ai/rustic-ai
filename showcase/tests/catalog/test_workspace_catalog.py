"""Execute the Personal Workspace catalog with actual agents and local provider clients."""

import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Message, Priority
from rustic_ai.mcp.models import CallToolResponse, ToolResult
from rustic_ai.showcase.catalog import load_blueprint


class WorkspaceLLM(LLM):
    def __init__(self, role, calls):
        self.role, self.calls = role, calls

    @property
    def model(self):
        return "local-workspace"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append((self.role, prompt))
        if len(self.calls) > 8:
            raise RuntimeError("Workspace flow exceeded its routing bound")
        if self.role == "summary_generator_agent":
            content = "Created the Harbor Notion page from the captured website."
        else:
            count = sum(role == self.role for role, _ in self.calls)
            intent, tool, arguments = [
                ("playwright", "browser_navigate", {"url": "https://example.test/harbor"}),
                ("notion", "API-post-page", {"title": "Harbor", "content": "CAPTURED_HARBOR_CONTENT"}),
                ("summarize", None, {}),
            ][count - 1]
            content = json.dumps(
                {
                    "intent": intent,
                    "user_friendly_plan": "Capture Harbor and create a page",
                    "actions": [{"tool_name": tool, "arguments": arguments}] if tool else [],
                }
            )
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class WorkspaceResolver(DependencyResolver[LLM]):
    calls: list[tuple[str, ChatCompletionRequest]] = []

    def resolve(self, org_id, guild_id, agent_id):
        return WorkspaceLLM(agent_id, self.calls)


def wait_for(predicate):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        if value := predicate():
            return value
        time.sleep(0.01)
    pytest.fail("Workspace catalog did not reach a terminal outcome")


@pytest.fixture
def workspace(monkeypatch, database):
    import rustic_ai.mcp.agent as mcp_agent
    import rustic_ai.vertexai.agents.content_moderation as moderation
    import rustic_ai.vertexai.client as vertex_client

    guilds, clients = [], []
    calls: list[tuple[str, ChatCompletionRequest]] = []
    blocked = {"value": False, "tool_error": False}

    class LocalMCPClient:
        def __init__(self, config, logger):
            self.service = "notion" if "NOTION_TOKEN" in config.env else "playwright"
            self.calls, self.discoveries = [], 0
            clients.append(self)

        async def list_tools(self):
            self.discoveries += 1
            return [SimpleNamespace(name="API-post-page" if self.service == "notion" else "browser_navigate")]

        async def call_tool(self, request):
            self.calls.append(request)
            if blocked["tool_error"]:
                return CallToolResponse(results=[], is_error=True, error="Local browser could not capture the page")
            text = "NOTION_PAGE_CREATED" if self.service == "notion" else "CAPTURED_HARBOR_CONTENT"
            return CallToolResponse(results=[ToolResult(type="text", content=text)])

    class LocalModerator:
        def moderate_text(self, document):
            return SimpleNamespace(
                moderation_categories=[SimpleNamespace(name="Toxic", confidence=1 if blocked["value"] else 0)]
            )

    monkeypatch.setattr(mcp_agent, "MCPClient", LocalMCPClient)
    monkeypatch.setattr(vertex_client.genai, "Client", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(moderation.language, "LanguageServiceClient", LocalModerator)

    def launch(flagged=False, tool_error=False):
        blocked["value"], blocked["tool_error"] = flagged, tool_error
        data = load_blueprint("personal_workspace.json")["spec"]
        data["id"] = "workspace-" + uuid4().hex
        WorkspaceResolver.calls = calls
        data["dependency_map"]["llm"] = {"class_name": WorkspaceResolver.get_qualified_class_name()}
        builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
        builder.add_agent_spec(
            AgentBuilder(UserProxyAgent)
            .set_id("entry")
            .set_name("Entry")
            .set_description("User entry")
            .set_properties({"user_id": "reader"})
            .listen_to_default_topic(False)
            .add_additional_topic(UserProxyAgent.get_user_inbox_topic("reader"))
            .build_spec()
        )
        builder.add_agent_spec(
            AgentBuilder(ProbeAgent)
            .set_id("observer")
            .set_name("Observer")
            .set_description("Outputs")
            .listen_to_default_topic(False)
            .add_additional_topic("user_message_broadcast")
            .add_additional_topic("error_topic")
            .build_spec()
        )
        guild = builder.bootstrap(database, "workspace-tests")
        wait_for(lambda: guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer"))
        guilds.append(guild)
        probe = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer").agent
        return guild, probe, calls, clients

    yield launch
    for guild in reversed(guilds):
        guild.shutdown()


def send_workspace(probe):
    request = ChatCompletionRequest(
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": "Capture https://example.test/harbor and create a Notion page"}],
            }
        ]
    )
    message = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
        payload=request.model_dump(),
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("reader"), message)


def test_workspace_capture_create_summary_preserves_action_history(workspace):
    _, probe, calls, clients = workspace()
    send_workspace(probe)
    terminal = wait_for(lambda: [m for m in probe.get_messages() if m.process_status == "completed"])
    assert len(terminal) == 1 and terminal[0].process_status == "completed", [m.payload for m in terminal]
    assert "Created the Harbor Notion page" in json.dumps(terminal[0].payload)
    assert [role for role, _ in calls] == ["workspace_orchestrator_agent"] * 3 + ["summary_generator_agent"]
    assert [(client.service, client.discoveries, len(client.calls)) for client in clients] == [
        ("notion", 1, 1),
        ("playwright", 1, 1),
    ]
    assert clients[1].calls[0].arguments["url"] == "https://example.test/harbor"
    assert clients[0].calls[0].arguments["content"] == "CAPTURED_HARBOR_CONTENT"
    after_capture = calls[1][1].model_dump_json()
    after_creation = calls[2][1].model_dump_json()
    summary = calls[3][1].model_dump_json()
    assert "browser_navigate" in after_capture and "CAPTURED_HARBOR_CONTENT" in after_capture
    assert "Capture https://example.test/harbor and create a Notion page" in after_capture
    assert "API-post-page" in after_creation and "NOTION_PAGE_CREATED" in after_creation
    assert all(
        value in summary
        for value in ["browser_navigate", "API-post-page", "CAPTURED_HARBOR_CONTENT", "NOTION_PAGE_CREATED"]
    )


def test_workspace_flagged_input_stops_before_models_and_external_tools(workspace):
    _, probe, calls, clients = workspace(flagged=True)
    send_workspace(probe)
    terminal = wait_for(lambda: [m for m in probe.get_messages() if m.process_status == "completed"])
    assert len(terminal) == 1 and terminal[0].process_status == "completed"
    assert "flagged" in json.dumps(terminal[0].payload) and not calls
    assert all(not client.calls and not client.discoveries for client in clients)


def test_workspace_mcp_error_stops_workflow_with_structured_error(workspace):
    _, probe, calls, clients = workspace(tool_error=True)
    send_workspace(probe)
    errors = wait_for(lambda: [m for m in probe.get_messages() if m.is_error_message])
    assert len(errors) == 1
    assert errors[0].payload["error_type"] == "ErrorProcessingMCPRequest"
    assert "Local browser" in errors[0].payload["error_message"]
    assert [role for role, _ in calls] == ["workspace_orchestrator_agent"]
    assert not clients[0].calls and len(clients[1].calls) == 1
    time.sleep(0.05)
    assert not [m for m in probe.get_messages() if m.process_status == "completed"]
