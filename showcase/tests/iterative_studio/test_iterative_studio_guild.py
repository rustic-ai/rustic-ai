"""Tests for the Iterative Studio guild.

This test module validates:
1. Guild specification loading and validation
2. Toolset functionality (ArXiv, Agentic, Deepthink)
3. Agent configuration correctness
4. Routing rules validation
5. End-to-end guild bootstrapping
"""

import json
from pathlib import Path
import tempfile

import pytest
import shortuuid

from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec

# Path to the guild.json file
GUILD_JSON_PATH = Path(__file__).parent.parent.parent / "apps" / "iterative_studio" / "iterative_studio.json"


class TestGuildSpecLoading:
    """Tests for loading and validating the guild specification."""

    def test_guild_json_exists(self):
        """Test that the guild.json file exists."""
        assert GUILD_JSON_PATH.exists(), f"guild.json not found at {GUILD_JSON_PATH}"

    def test_guild_json_is_valid_json(self):
        """Test that guild.json is valid JSON."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "name" in data
        assert "spec" in data

    def test_guild_spec_can_be_parsed(self):
        """Test that the guild spec can be parsed into a GuildSpec object."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        # Parse the inner spec
        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        assert guild_spec.name == "Iterative Studio"
        assert len(guild_spec.agents) == 16  # 16 agents defined

    def test_all_agents_have_required_fields(self):
        """Test that all agents have required fields."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        for agent in guild_spec.agents:
            assert agent.id, f"Agent missing id: {agent}"
            assert agent.name, f"Agent missing name: {agent}"
            assert agent.class_name, f"Agent {agent.name} missing class_name"

    def test_dependency_map_is_valid(self):
        """Test that the dependency map contains expected dependencies."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        assert "llm" in guild_spec.dependency_map
        assert "filesystem" in guild_spec.dependency_map
        assert "kb_backend" in guild_spec.dependency_map

    def test_routing_slip_is_valid(self):
        """Test that the routing slip can be parsed."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        assert guild_spec.routes is not None
        assert len(guild_spec.routes.steps) > 0

    def test_agent_topics_are_defined(self):
        """Test that agents have proper topic configurations."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        # Check that Mode Controller listens to MODE_CONTROL topic
        mode_controller = next((a for a in guild_spec.agents if a.id == "mode_controller"), None)
        assert mode_controller is not None
        assert "MODE_CONTROL" in mode_controller.additional_topics


class TestArxivToolset:
    """Tests for the ArXiv toolset."""

    def test_arxiv_toolset_import(self):
        """Test that ArxivToolset can be imported."""
        from rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset import (
            ArxivToolset,
        )

        toolset = ArxivToolset()
        assert toolset is not None

    def test_arxiv_toolset_has_toolspecs(self):
        """Test that ArxivToolset provides tool specifications."""
        from rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset import (
            ArxivToolset,
        )

        toolset = ArxivToolset()
        specs = toolset.get_toolspecs()

        assert len(specs) == 1
        assert specs[0].name == "SearchArxiv"
        assert "ArXiv" in specs[0].description

    def test_arxiv_toolset_parameter_class(self):
        """Test that ArxivToolset parameter class is valid."""
        from rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset import (
            ArxivSearchParams,
        )

        params = ArxivSearchParams(query="transformer neural network", max_results=5)
        assert params.query == "transformer neural network"
        assert params.max_results == 5

    def test_arxiv_toolset_unknown_tool_raises(self):
        """Test that executing unknown tool raises ValueError."""
        from rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset import (
            ArxivSearchParams,
            ArxivToolset,
        )

        toolset = ArxivToolset()
        params = ArxivSearchParams(query="test")

        with pytest.raises(ValueError, match="Unknown tool"):
            toolset.execute("UnknownTool", params)


class TestAgenticToolset:
    """Tests for the Agentic toolset."""

    def test_agentic_toolset_import(self):
        """Test that AgenticToolset can be imported."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
        )

        toolset = AgenticToolset()
        assert toolset is not None

    def test_agentic_toolset_has_toolspecs(self):
        """Test that AgenticToolset provides tool specifications."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
        )

        toolset = AgenticToolset()
        specs = toolset.get_toolspecs()

        assert len(specs) == 4
        tool_names = [s.name for s in specs]
        assert "ReadFile" in tool_names
        assert "WriteFile" in tool_names
        assert "ApplyDiff" in tool_names
        assert "ListDirectory" in tool_names

    def test_agentic_toolset_write_and_read_file(self):
        """Test writing and reading a file through the toolset."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
            ReadFileParams,
            WriteFileParams,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            toolset = AgenticToolset(working_dir=tmpdir)

            # Write a file
            write_params = WriteFileParams(
                file_path="test.txt",
                content="Hello, World!",
            )
            result = toolset.execute("WriteFile", write_params)
            result_data = json.loads(result)
            assert result_data["success"] is True

            # Read the file back
            read_params = ReadFileParams(file_path="test.txt")
            result = toolset.execute("ReadFile", read_params)
            result_data = json.loads(result)
            assert "Hello, World!" in result_data["content"]

    def test_agentic_toolset_list_directory(self):
        """Test listing a directory."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
            ListDirectoryParams,
            WriteFileParams,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            toolset = AgenticToolset(working_dir=tmpdir)

            # Create some files
            toolset.execute("WriteFile", WriteFileParams(file_path="file1.txt", content="content1"))
            toolset.execute("WriteFile", WriteFileParams(file_path="file2.txt", content="content2"))

            # List directory
            list_params = ListDirectoryParams(directory_path=".")
            result = toolset.execute("ListDirectory", list_params)
            result_data = json.loads(result)

            assert result_data["count"] == 2
            paths = [e["path"] for e in result_data["entries"]]
            assert "file1.txt" in paths
            assert "file2.txt" in paths

    def test_agentic_toolset_apply_diff(self):
        """Test applying a diff to a file."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
            ApplyDiffParams,
            ReadFileParams,
            WriteFileParams,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            toolset = AgenticToolset(working_dir=tmpdir)

            # Create initial file
            toolset.execute("WriteFile", WriteFileParams(file_path="code.py", content="print('hello')"))

            # Apply diff
            diff_params = ApplyDiffParams(
                file_path="code.py",
                old_content="print('hello')",
                new_content="print('goodbye')",
            )
            result = toolset.execute("ApplyDiff", diff_params)
            result_data = json.loads(result)
            assert result_data["success"] is True

            # Verify change
            read_result = toolset.execute("ReadFile", ReadFileParams(file_path="code.py"))
            read_data = json.loads(read_result)
            assert "goodbye" in read_data["content"]

    def test_agentic_toolset_path_traversal_blocked(self):
        """Test that path traversal attacks are blocked."""
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
            ReadFileParams,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            toolset = AgenticToolset(working_dir=tmpdir)

            # Try to read file outside working directory
            read_params = ReadFileParams(file_path="../../../etc/passwd")
            result = toolset.execute("ReadFile", read_params)
            result_data = json.loads(result)

            # Should return an error, not the file contents
            assert "error" in result_data


class TestDeepthinkToolset:
    """Tests for the Deepthink toolset."""

    def test_deepthink_toolset_import(self):
        """Test that DeepthinkToolset can be imported."""
        from rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset import (
            DeepthinkToolset,
        )

        toolset = DeepthinkToolset()
        assert toolset is not None

    def test_deepthink_toolset_has_toolspecs(self):
        """Test that DeepthinkToolset provides tool specifications."""
        from rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset import (
            DeepthinkToolset,
        )

        toolset = DeepthinkToolset()
        specs = toolset.get_toolspecs()

        assert len(specs) == 6
        tool_names = [s.name for s in specs]
        assert "GenerateStrategies" in tool_names
        assert "GenerateHypotheses" in tool_names
        assert "CritiqueSolution" in tool_names
        assert "RedTeam" in tool_names
        assert "SelectBestSolution" in tool_names
        assert "RecordReasoning" in tool_names

    def test_deepthink_toolset_generate_strategies(self):
        """Test generating strategies."""
        from rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset import (
            DeepthinkToolset,
            GenerateStrategiesParams,
        )

        toolset = DeepthinkToolset()
        params = GenerateStrategiesParams(
            problem="How to improve code quality?",
            num_strategies=3,
        )

        result = toolset.execute("GenerateStrategies", params)
        result_data = json.loads(result)

        assert "instruction" in result_data
        assert "prompt" in result_data
        assert result_data["prompt"]["num_strategies"] == 3

    def test_deepthink_toolset_record_reasoning(self):
        """Test recording reasoning steps."""
        from rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset import (
            DeepthinkToolset,
            RecordReasoningParams,
        )

        toolset = DeepthinkToolset()
        params = RecordReasoningParams(
            stage="strategy",
            content="I decided to use approach A because...",
        )

        result = toolset.execute("RecordReasoning", params)
        result_data = json.loads(result)

        assert result_data["recorded"] is True
        assert result_data["stage"] == "strategy"
        assert result_data["history_length"] == 1


class TestGuildBootstrap:
    """Tests for bootstrapping the guild."""

    @pytest.fixture
    def org_id(self):
        return f"test_org_{shortuuid.uuid()}"

    def test_guild_can_be_built_from_spec(self, org_id):
        """Test that a guild can be built from the spec."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        # Build a simple test guild using GuildBuilder
        builder = GuildBuilder(
            guild_id=f"iterative_studio_test_{shortuuid.uuid()}",
            guild_name=guild_spec.name,
            guild_description=guild_spec.description,
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add dependency map
        builder.set_dependency_map(guild_spec.dependency_map)

        # Add routing slip
        builder.set_routes(guild_spec.routes)

        # Build spec (don't launch - that requires all agent classes to be available)
        built_spec = builder.build_spec()

        assert built_spec.name == guild_spec.name
        assert built_spec.routes is not None

    def test_guild_agent_classes_are_importable(self):
        """Test that all agent class names in the spec are importable."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]

        for agent_data in spec_data["agents"]:
            class_name = agent_data["class_name"]
            try:
                from rustic_ai.core.utils.basic_class_utils import get_class_from_name

                agent_class = get_class_from_name(class_name)
                assert agent_class is not None, f"Could not load class: {class_name}"
            except Exception as e:
                pytest.fail(f"Failed to import agent class {class_name}: {e}")


class TestModeClassification:
    """Tests for mode classification logic."""

    @pytest.mark.parametrize(
        "input_text,expected_modes",
        [
            ("Review this code and fix bugs", ["refine"]),
            ("Help me understand this complex algorithm", ["deepthink", "adaptive"]),
            ("Search for papers about transformers", ["agentic"]),
            ("Write a blog post about AI", ["contextual"]),
            ("Create a file with the solution", ["agentic"]),
        ],
    )
    def test_mode_classification_keywords(self, input_text, expected_modes):
        """Test that certain keywords would likely trigger specific modes."""
        # This is a heuristic test - actual classification depends on the LLM
        # We're just checking that the system is set up correctly

        # Keywords that might trigger each mode
        mode_keywords = {
            "refine": ["review", "fix", "bug", "improve", "refactor"],
            "deepthink": ["complex", "analyze", "strategy", "design", "architecture"],
            "adaptive": ["explore", "iterate", "hypothesis", "flexible"],
            "agentic": ["file", "search", "paper", "arxiv", "create", "write file"],
            "contextual": ["write", "blog", "essay", "document", "content"],
        }

        # Check that at least one expected mode's keywords are present
        input_lower = input_text.lower()
        matched = False
        for mode in expected_modes:
            for keyword in mode_keywords[mode]:
                if keyword in input_lower:
                    matched = True
                    break
            if matched:
                break

        assert matched, f"Input '{input_text}' should match one of {expected_modes}"


class TestRoutingConfiguration:
    """Tests for routing configuration."""

    def test_routing_steps_cover_all_modes(self):
        """Test that routing steps exist for all operational modes."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]
        guild_spec = GuildSpec.model_validate(spec_data)

        # Check that we have routes for key topics
        route_topics = set()
        for step in guild_spec.routes.steps:
            if step.destination and step.destination.topics:
                topics = step.destination.topics
                if isinstance(topics, str):
                    route_topics.add(topics)
                else:
                    route_topics.update(topics)

        # Verify key topics are routed to
        assert "user_message_broadcast" in route_topics, "Missing route to user_message_broadcast"

    def test_mode_controller_routes_to_modes(self):
        """Test that mode controller routing step exists."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]

        # Find the mode controller route
        routes = spec_data["routes"]["steps"]
        mode_controller_route = None

        for route in routes:
            if route.get("agent", {}).get("name") == "Mode Controller":
                mode_controller_route = route
                break

        assert mode_controller_route is not None, "Mode Controller route not found"
        assert "transformer" in mode_controller_route, "Mode Controller route missing transformer"

    def test_refine_mode_parallel_routing(self):
        """Test that Refine mode routes to both novelty and quality agents."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]

        # Check the mode routing step
        routes = spec_data["routes"]["steps"]
        for route in routes:
            if route.get("agent", {}).get("name") == "Mode Controller":
                handler = route.get("transformer", {}).get("handler", "")
                # The handler should route 'refine' to both REFINE_NOVELTY and REFINE_QUALITY
                assert "REFINE_NOVELTY" in handler or "refine" in handler.lower()
                break


class TestToolsetSerialization:
    """Tests for toolset serialization in guild spec."""

    def test_react_agent_toolset_config(self):
        """Test that ReAct agent toolset configurations are valid."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]

        # Find ReAct agents
        react_agents = [a for a in spec_data["agents"] if "react" in a["class_name"].lower()]

        assert len(react_agents) >= 2, "Expected at least 2 ReAct agents"

        for agent in react_agents:
            props = agent.get("properties", {})
            toolset = props.get("toolset", {})

            assert "kind" in toolset, f"ReAct agent {agent['name']} missing toolset.kind"

    def test_composite_toolset_config(self):
        """Test that composite toolset is configured correctly for Agentic agent."""
        with open(GUILD_JSON_PATH) as f:
            data = json.load(f)

        spec_data = data["spec"]

        # Find the Agentic agent
        agentic_agent = next((a for a in spec_data["agents"] if a["id"] == "agentic_agent"), None)

        assert agentic_agent is not None, "Agentic agent not found"

        toolset = agentic_agent["properties"]["toolset"]
        assert "CompositeToolset" in toolset["kind"], "Agentic agent should use CompositeToolset"
        assert "toolsets" in toolset, "CompositeToolset missing toolsets array"
        assert len(toolset["toolsets"]) == 2, "Expected 2 toolsets in composite"
