from abc import ABC, abstractmethod
import time

from pydantic import BaseModel, JsonValue
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import (
    Agent,
    AgentDependency,
    ProcessContext,
)
from rustic_ai.core.guild.agent_ext.depends.kvstore.base import BaseKVStore
from rustic_ai.core.guild.agent_ext.depends.kvstore.in_memory_kvstore import (
    InMemoryKVStoreResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class KVPut(BaseModel):
    key: str
    value: JsonValue
    in_guild_store: bool = False


class KVResponse(BaseModel):
    key: str
    value: JsonValue
    method: str
    guild_store: bool = False


class KVGet(BaseModel):
    key: str
    from_guild_store: bool = False


class KVDel(BaseModel):
    key: str
    from_guild_store: bool = False


class KeyNotFound(BaseModel):
    key: str


class KVStoreAgent(Agent):
    """
    Agent for testing KVStore dependencies
    """

    @agent.processor(
        KVPut,
        depends_on=[
            "kvstore",
            AgentDependency(
                dependency_key="kvstore",
                dependency_var="guild_kvstore",
                guild_level=True,
            ),
        ],
    )
    def store_kv(
        self,
        ctx: ProcessContext[KVPut],
        kvstore: BaseKVStore,
        guild_kvstore: BaseKVStore,
    ):
        """
        Handles messages of type KVPut
        """
        data: KVPut = ctx.payload
        if data.in_guild_store:
            guild_kvstore.set(data.key, data.value)
        else:
            kvstore.set(data.key, data.value)

        ctx.send(
            KVResponse(
                key=data.key,
                value=data.value,
                method="PUT",
                guild_store=data.in_guild_store,
            )
        )

    @agent.processor(
        KVGet,
        depends_on=[
            "kvstore",
            AgentDependency(
                dependency_key="kvstore",
                dependency_var="guild_kvstore",
                guild_level=True,
            ),
        ],
    )
    def get_kv(
        self,
        ctx: ProcessContext[KVGet],
        kvstore: BaseKVStore,
        guild_kvstore: BaseKVStore,
    ):
        """
        Handles messages of type KVGet
        """
        data: KVGet = ctx.payload
        if data.from_guild_store:
            value = guild_kvstore.get(data.key)
        else:
            value = kvstore.get(data.key)

        if value:
            resp = KVResponse(
                key=data.key,
                value=value,
                method="GET",
                guild_store=data.from_guild_store,
            )

            ctx.send(resp)
        else:
            ctx.send(KeyNotFound(key=data.key))

    @agent.processor(
        KVDel,
        depends_on=[
            "kvstore",
            AgentDependency(
                dependency_key="kvstore",
                dependency_var="guild_kvstore",
                guild_level=True,
            ),
        ],
    )
    def del_kv(
        self,
        ctx: ProcessContext[KVDel],
        kvstore: BaseKVStore,
        guild_kvstore: BaseKVStore,
    ):
        """
        Handles messages of type KVDel
        """
        data: KVDel = ctx.payload
        if data.from_guild_store:
            guild_kvstore.delete(data.key)
        else:
            kvstore.delete(data.key)

        ctx.send(
            KVResponse(
                key=data.key,
                value=None,
                method="DEL",
                guild_store=data.from_guild_store,
            )
        )


class BaseTestKVStore(ABC):

    @pytest.fixture
    @abstractmethod
    def dep_map(self) -> dict:
        """
        Fixture that returns dependency mapping of the storage implementation being tested.
        This should be overridden in subclasses that test specific storage implementations.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    def test_kvstore(self, probe_spec, dep_map: dict, org_id):
        agent_spec: AgentSpec = (
            AgentBuilder(KVStoreAgent).set_description("KV Store Agent").set_name("KVStoreAgent").build_spec()
        )

        guild_builder = (
            GuildBuilder("test_guild", "Test Guild", "Guild to test KV Store Agent")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )
        guild = guild_builder.launch(organization_id=org_id)

        if "kvstore" in dep_map:
            guild.dependency_map["kvstore"].class_name = dep_map["kvstore"].class_name
        else:
            guild.dependency_map["kvstore"].class_name = InMemoryKVStoreResolver.get_qualified_class_name()

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVPut(key="key1", value=42).model_dump(),
            format=KVPut,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVGet(key="key1").model_dump(),
            format=KVGet,
        )

        time.sleep(0.5)

        messages = probe_agent.get_messages()

        assert len(messages) == 2

        assert messages[0].payload["key"] == "key1"
        assert messages[0].payload["value"] == 42

        assert messages[1].payload["key"] == "key1"
        assert messages[1].payload["value"] == 42

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVPut(key="key1", value=43, in_guild_store=True).model_dump(),
            format=KVPut,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVGet(key="key1", from_guild_store=True).model_dump(),
            format=KVGet,
        )

        time.sleep(0.5)

        messages = probe_agent.get_messages()

        assert len(messages) == 2

        assert messages[0].payload["key"] == "key1"
        assert messages[0].payload["value"] == 43

        assert messages[1].payload["key"] == "key1"
        assert messages[1].payload["value"] == 43

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVDel(key="key1").model_dump(),
            format=KVDel,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVGet(key="key1").model_dump(),
            format=KVGet,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVGet(key="key1", from_guild_store=True).model_dump(),
            format=KVGet,
        )

        time.sleep(0.05)
        messages = probe_agent.get_messages()

        assert len(messages) == 3

        assert messages[0].payload["key"] == "key1"
        assert messages[0].payload["value"] is None
        assert messages[0].payload["method"] == "DEL"

        assert messages[1].payload["key"] == "key1"
        assert messages[1].format == get_qualified_class_name(KeyNotFound)

        assert messages[2].payload["key"] == "key1"
        assert messages[2].payload["value"] == 43

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVDel(key="key1", from_guild_store=True).model_dump(),
            format=KVDel,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=KVGet(key="key1", from_guild_store=True).model_dump(),
            format=KVGet,
        )

        time.sleep(0.5)

        messages = probe_agent.get_messages()

        assert len(messages) == 2

        assert messages[0].payload["key"] == "key1"
        assert messages[0].payload["value"] is None

        assert messages[1].payload["key"] == "key1"
        assert messages[1].format == get_qualified_class_name(KeyNotFound)

        guild.shutdown()
