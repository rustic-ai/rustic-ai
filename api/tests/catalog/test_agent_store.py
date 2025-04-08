import pytest

from rustic_ai.api_server.catalog.catalog_store import CatalogStore
from rustic_ai.core.guild.metaprog.agent_registry import AgentEntry, HandlerEntry
from rustic_ai.core.guild.metastore.database import Metastore


class TestAgentCatalog:
    @pytest.fixture(scope="module")
    def catalog_engine(self):
        db = "sqlite:///agent_store_test.db"
        Metastore.drop_db(unsafe=True)
        Metastore.initialize_engine(db)
        yield Metastore.get_engine()
        Metastore.drop_db(unsafe=True)

    @pytest.fixture
    def catalog_store(self, catalog_engine):
        return CatalogStore(catalog_engine)

    def test_agent_actions(self, catalog_store: CatalogStore):
        new_agent_1 = AgentEntry(
            agent_name="TestAgent",
            qualified_class_name="rustic_ai.agents.test.TestAgent",
            agent_doc="Test agent",
            agent_props_schema={
                "description": "Test agent properties",
                "properties": {},
                "title": "TestAgentProps",
                "type": "object",
            },
            message_handlers={
                "test_message": HandlerEntry(
                    handler_name="test_message",
                    message_format="generic_json1",
                    message_format_schema={"type": "object"},
                    handler_doc="Test message handler1",
                    send_message_calls=[],
                )
            },
            agent_dependencies=[],
        )

        # Create the second agent entry
        new_agent_2 = AgentEntry(
            agent_name="AnotherTestAgent",
            qualified_class_name="rustic_ai.agents.test.AnotherTestAgent",
            agent_doc="Another test agent",
            agent_props_schema={
                "description": "Another test agent properties",
                "properties": {},
                "title": "AnotherTestAgentProps",
                "type": "object",
            },
            message_handlers={
                "test_message": HandlerEntry(
                    handler_name="test_message",
                    message_format="generic_json2",
                    message_format_schema={"type": "object", "name": "agent_2_schema"},
                    handler_doc="Test message handler2",
                    send_message_calls=[],
                )
            },
            agent_dependencies=[],
        )

        catalog_store.register_agent(new_agent_1)
        catalog_store.register_agent(new_agent_2)

        agent_response_1 = catalog_store.get_agent_by_class_name("rustic_ai.agents.test.TestAgent")
        assert agent_response_1.agent_name == new_agent_1.agent_name
        assert agent_response_1.qualified_class_name == new_agent_1.qualified_class_name
        assert agent_response_1.agent_doc == new_agent_1.agent_doc
        assert agent_response_1.agent_props_schema == new_agent_1.agent_props_schema
        assert agent_response_1.message_handlers == new_agent_1.message_handlers
        assert agent_response_1.agent_dependencies == new_agent_1.agent_dependencies

        agents = catalog_store.get_agents()
        assert new_agent_1.qualified_class_name in agents
        assert new_agent_2.qualified_class_name in agents
        assert agents[new_agent_1.qualified_class_name].agent_name == new_agent_1.agent_name
        assert agents[new_agent_2.qualified_class_name].agent_name == new_agent_2.agent_name

        agents_filtered = catalog_store.get_agents(class_names=["rustic_ai.agents.test.AnotherTestAgent"])
        assert new_agent_1.qualified_class_name not in agents_filtered
        assert new_agent_2.qualified_class_name in agents_filtered

        agent_message_format_schema = catalog_store.get_agent_by_message_format("generic_json2")
        assert "agent_2_schema" in agent_message_format_schema["name"]
