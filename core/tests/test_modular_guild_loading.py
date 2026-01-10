import os

import pytest

from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.messaging.core.message import FunctionalTransformer, RoutingSlip


class TestModularGuildLoading:
    def test_load_modular_guild(self):
        """
        Verify that a guild with !include and !code tags is loaded correctly.
        """
        # Path to the modular guild resource
        base_path = os.path.dirname(__file__)
        guild_yaml_path = os.path.join(base_path, "resources/modular_guild/guild.yaml")

        # Load the guild using the builder
        builder = GuildBuilder.from_yaml_file(guild_yaml_path)
        spec = builder.build_spec()

        # Verify Guild Properties
        assert spec.id == "modular_guild_id"
        assert spec.name == "modular_guild_name"
        assert spec.description == "description for modular_guild"

        # Verify Agents loaded via !include
        assert len(spec.agents) == 1
        agent = spec.agents[0]
        assert agent.name == "Modular Agent"
        assert agent.description == "A simple agent defined in a separate file"
        assert agent.class_name == "rustic_ai.core.agents.eip.basic_wiring_agent.BasicWiringAgent"

        # Verify Routes loaded via !include and script loaded via !code
        assert spec.routes is not None
        assert isinstance(spec.routes, RoutingSlip)
        assert len(spec.routes.steps) == 1

        step = spec.routes.steps[0]
        assert step.agent.name == "Modular Agent"
        assert isinstance(step.transformer, FunctionalTransformer)

        # Verify the content of the script loaded via !code
        expected_script = '({"topics": payload.routing_key})'
        assert step.transformer.handler.strip() == expected_script.strip()


if __name__ == "__main__":
    pytest.main([__file__])
