import importlib

import pytest
import shortuuid

from rustic_ai.core.guild.builders import (
    GuildBuilder,
    GuildHelper,
)
from rustic_ai.core.messaging import MessagingConfig

from .simple_agent import SimpleAgentWithProps


class TestGuildBuilderWithVariables:

    exec_engine_clz: str = "rustic_ai.core.guild.execution.sync.sync_exec_@engine.SyncExecutionEngine"

    @pytest.fixture(
        scope="function",  # Changed from class to function to access messaging_server
        params=[
            pytest.param(
                "InMemoryMessagingBackend",
                id="InMemoryMessagingBackend",
            ),
            pytest.param(
                "EmbeddedMessagingBackend",
                id="EmbeddedMessagingBackend",
            ),
        ],
    )
    def messaging(self, request, messaging_server) -> MessagingConfig:
        backend_type = request.param

        if backend_type == "InMemoryMessagingBackend":
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend",
                backend_class="InMemoryMessagingBackend",
                backend_config={},
            )
        elif backend_type == "EmbeddedMessagingBackend":
            # Use the shared messaging server from conftest.py
            server, port = messaging_server
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend.embedded_backend",
                backend_class="EmbeddedMessagingBackend",
                backend_config={"auto_start_server": False, "port": port},
            )
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    @pytest.fixture
    def guild_id(self):
        return f"test_guild_id_{shortuuid.uuid()}"

    @pytest.fixture
    def guild_name(self):
        return "test_guild_name"

    @pytest.fixture
    def guild_description(self, guild_name):
        return f"description for {guild_name}"

    def test_guild_from_yaml_with_var(
        self,
        guild_id: str,
        guild_name: str,
        guild_description: str,
    ):
        yaml_path = importlib.resources.files("core.tests.resources.guild_specs").joinpath("test_guild_with_variables.yaml")  # type: ignore
        new_spec = GuildBuilder.from_yaml_file(yaml_path).build_spec()

        assert new_spec.name == guild_name
        assert new_spec.description == guild_description
        assert new_spec.agents[0].name == "asdf"
        assert new_spec.agents[0].description == "asdf - A simple agent with variable properties"
        assert new_spec.agents[0].class_name == SimpleAgentWithProps.get_qualified_class_name()
        assert new_spec.agents[0].properties.model_dump() == {"prop1": "custom/model_1", "prop2": 2}

        msgconf = GuildHelper.get_messaging_config(new_spec)

        # This is not parameterized as we are testing initialization from a YAML file
        assert msgconf.backend_module == "rustic_ai.core.messaging.backend.embedded_backend"
        assert msgconf.backend_class == "EmbeddedMessagingBackend"
        assert msgconf.backend_config == {}

    def test_guild_from_json_with_var(
        self,
        guild_id: str,
        guild_name: str,
        guild_description: str,
    ):
        yaml_path = importlib.resources.files("core.tests.resources.guild_specs").joinpath("test_guild_with_variables.json")  # type: ignore
        new_spec = GuildBuilder.from_json_file(yaml_path).build_spec()

        assert new_spec.name == guild_name
        assert new_spec.description == guild_description
        assert new_spec.agents[0].name == "asdf"
        assert new_spec.agents[0].description == "asdf - A simple agent with variable properties"
        assert new_spec.agents[0].class_name == SimpleAgentWithProps.get_qualified_class_name()
        assert new_spec.agents[0].properties.model_dump() == {"prop1": "custom/model_1", "prop2": 2}

        msgconf = GuildHelper.get_messaging_config(new_spec)

        # This is not parameterized as we are testing initialization from a YAML file
        assert msgconf.backend_module == "rustic_ai.core.messaging.backend.embedded_backend"
        assert msgconf.backend_class == "EmbeddedMessagingBackend"
        assert msgconf.backend_config == {"auto_start_server": True}
