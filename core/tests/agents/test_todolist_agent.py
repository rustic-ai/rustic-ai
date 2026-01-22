import asyncio
from datetime import datetime, timedelta
import os
import time

import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics
from rustic_ai.core.agents.planners.todolist_agent import (
    AddTaskRequest,
    DeleteTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    NextTaskRequest,
    TaskCompletedEvent,
    TaskStatus,
    TaskUnblockedEvent,
    TodoListAgent,
    UpdateStatusRequest,
    UpdateTaskRequest,
)
from rustic_ai.core.agents.system.models import UserAgentCreationRequest
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils import GemstoneGenerator, Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class TestTodoListGuild:

    async def wait_for_message(self, probe_agent, check_fn, timeout=10.0, interval=0.1):
        """
        Waits for a message satisfying check_fn to appear in probe_agent messages.

        :param probe_agent: ProbeAgent
        :param check_fn: function taking Message -> bool
        :param timeout: max seconds to wait
        :param interval: time between polls
        :return: the matching message or None
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check ALL messages, not just the last one
            for msg in probe_agent.get_messages():
                if check_fn(msg):
                    return msg
            await asyncio.sleep(interval)

        # Debug: print all messages on timeout
        print(f"\n=== Timeout! All messages received ({len(probe_agent.get_messages())}) ===")
        for i, msg in enumerate(probe_agent.get_messages()):
            print(f"{i}: format={msg.format}, topic={msg.topic_published_to}, sender={msg.sender.id}")

        raise TimeoutError("Timeout waiting for matching message.")

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///test_todolist_guild.db"

        if os.path.exists("test_todolist_guild.db"):
            os.remove("test_todolist_guild.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def todolist_guild(self, rgdatabase):
        guild_builder = GuildBuilder(
            guild_id=f"todolist_guild_{shortuuid.uuid()}",
            guild_name="TODO Guild",
            guild_description="Manage TODOs",
        )

        todo_agent = (
            AgentBuilder(TodoListAgent)
            .set_id("todo_agent")
            .set_name("TODO Agent")
            .set_description("An agent for managing TODO tasks")
            .build_spec()
        )

        guild_builder.add_agent_spec(todo_agent)

        guild = guild_builder.bootstrap(rgdatabase, "test_org")
        yield guild
        guild.shutdown()

    @pytest.mark.asyncio
    async def test_todo_flow(self, todolist_guild: Guild):
        generator = GemstoneGenerator(17)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Step 1: Add a task
        task_id = shortuuid.uuid()
        add_request = AddTaskRequest(
            id=task_id,
            todo="Write unit tests",
            start_time=datetime.now().isoformat(),
            deadline=(datetime.now() + timedelta(days=1)).isoformat(),
            depends_on=[],
        )

        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=add_request.model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        await asyncio.sleep(10)

        # Step 2: Get the task
        get_request = GetTaskRequest(id=task_id)
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=get_request.model_dump(),
                format=get_qualified_class_name(GetTaskRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        get_task_response = await self.wait_for_message(
            probe_agent,
            lambda m: "GetTaskResponse" in m.format,
        )
        assert get_task_response.payload["task"]["todo"] == "Write unit tests"

        # Step 3: Update task
        probe_agent.clear_messages()  # Clear before sending update
        update_request = UpdateTaskRequest(
            id=task_id,
            todo="Write better unit tests",
        )

        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=update_request.model_dump(),
                format=get_qualified_class_name(UpdateTaskRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        await asyncio.sleep(5)  # Give time for update to process

        # Step 4: Get next pending task
        probe_agent.clear_messages()  # Clear before getting next task
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload={"sort_by": "start_time"},
                format=get_qualified_class_name(NextTaskRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        next_task_messages = await self.wait_for_message(
            probe_agent,
            lambda m: "GetTaskResponse" in m.format,
        )
        assert next_task_messages.payload["task"]["todo"] == "Write better unit tests"

        # Step 5: Delete task
        delete_request = DeleteTaskRequest(id=task_id)
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=delete_request.model_dump(),
                format=get_qualified_class_name(DeleteTaskRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        await asyncio.sleep(10)

        # Step 6: List task
        list_request = ListTasksRequest(status=TaskStatus.PENDING)
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=list_request.model_dump(),
                format=get_qualified_class_name(ListTasksRequest),
                sender=AgentTag(id="test_agent"),
            ),
        )

        list_reponse = await self.wait_for_message(
            probe_agent,
            lambda m: "ListTasksResponse" in m.format,
        )
        assert len(list_reponse.payload["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_dependency_chain_unblock_events(self, todolist_guild: Guild):
        """Test that completing dependencies emits TaskUnblockedEvent."""
        generator = GemstoneGenerator(18)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_deps")
            .set_name("Test Agent Deps")
            .set_description("A test probe agent for dependency tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_deps"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user_deps", user_name="test_user_deps").model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Create child tasks (dependencies)
        child1_id = "child-task-1"
        child2_id = "child-task-2"
        parent_id = "parent-task"
        correlation = "test-workflow-123"

        # Add child task 1
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_deps"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=child1_id,
                    todo="Child task 1",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                    correlation_id=correlation,
                    metadata={"phase": "intel", "type": "news"},
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_deps"),
            ),
        )

        # Add child task 2
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_deps"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=child2_id,
                    todo="Child task 2",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                    correlation_id=correlation,
                    metadata={"phase": "intel", "type": "financial"},
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_deps"),
            ),
        )

        await asyncio.sleep(2)

        # Add parent task that depends on both children
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_deps"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=parent_id,
                    todo="Parent task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[child1_id, child2_id],
                    correlation_id=correlation,
                    metadata={"phase": "aggregation"},
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_deps"),
            ),
        )

        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete child task 1 - parent should remain blocked
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_deps"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=child1_id, status=TaskStatus.DONE).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_deps"),
            ),
        )

        # Wait for TaskCompletedEvent for child1
        completed_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskCompletedEvent" in m.format and m.payload.get("task_id") == child1_id,
        )
        assert completed_event.payload["correlation_id"] == correlation

        await asyncio.sleep(2)

        # Verify no TaskUnblockedEvent yet (parent still has one dependency)
        unblocked_messages = [
            m for m in probe_agent.get_messages() if "TaskUnblockedEvent" in m.format
        ]
        assert len(unblocked_messages) == 0, "Parent should still be blocked"

        probe_agent.clear_messages()

        # Complete child task 2 - parent should now be unblocked
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_deps"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=child2_id, status=TaskStatus.DONE).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_deps"),
            ),
        )

        # Wait for TaskUnblockedEvent for parent
        unblocked_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskUnblockedEvent" in m.format,
        )
        assert unblocked_event.payload["task_id"] == parent_id
        assert unblocked_event.payload["correlation_id"] == correlation
        assert unblocked_event.payload["task"]["status"] == TaskStatus.PENDING
        assert unblocked_event.payload["task"]["metadata"]["phase"] == "aggregation"

    @pytest.mark.asyncio
    async def test_list_tasks_all_statuses(self, todolist_guild: Guild):
        """Test that ListTasksRequest with status=None or ALL returns all tasks."""
        generator = GemstoneGenerator(19)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_list")
            .set_name("Test Agent List")
            .set_description("A test probe agent for list tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_list"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user_list", user_name="test_user_list").model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Add a pending task
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_list"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id="task-pending",
                    todo="Pending task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_list"),
            ),
        )

        await asyncio.sleep(2)

        # List with status=None should return all tasks
        probe_agent.clear_messages()
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_list"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=ListTasksRequest(status=None).model_dump(),
                format=get_qualified_class_name(ListTasksRequest),
                sender=AgentTag(id="test_agent_list"),
            ),
        )

        list_response = await self.wait_for_message(
            probe_agent,
            lambda m: "ListTasksResponse" in m.format,
        )
        assert len(list_response.payload["tasks"]) == 1

        # List with status=ALL should also return all tasks
        probe_agent.clear_messages()
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_list"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=ListTasksRequest(status=TaskStatus.ALL).model_dump(),
                format=get_qualified_class_name(ListTasksRequest),
                sender=AgentTag(id="test_agent_list"),
            ),
        )

        list_response_all = await self.wait_for_message(
            probe_agent,
            lambda m: "ListTasksResponse" in m.format,
        )
        assert len(list_response_all.payload["tasks"]) == 1

    @pytest.mark.asyncio
    async def test_correlation_id_and_metadata(self, todolist_guild: Guild):
        """Test that correlation_id and metadata are persisted and returned."""
        generator = GemstoneGenerator(20)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_meta")
            .set_name("Test Agent Meta")
            .set_description("A test probe agent for metadata tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_meta"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user_meta", user_name="test_user_meta").model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        task_id = "task-with-metadata"
        correlation = "acme-corp-dossier"
        metadata = {"company": "Acme Corp", "phase": "intel", "file_path": "/tmp/dossier/acme/intel.md"}

        # Add task with correlation_id and metadata
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_meta"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=task_id,
                    todo="Task with metadata",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                    correlation_id=correlation,
                    metadata=metadata,
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_meta"),
            ),
        )

        await asyncio.sleep(2)

        # Get the task and verify metadata is preserved
        probe_agent.clear_messages()
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_meta"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=GetTaskRequest(id=task_id).model_dump(),
                format=get_qualified_class_name(GetTaskRequest),
                sender=AgentTag(id="test_agent_meta"),
            ),
        )

        get_response = await self.wait_for_message(
            probe_agent,
            lambda m: "GetTaskResponse" in m.format,
        )
        task = get_response.payload["task"]
        assert task["correlation_id"] == correlation
        assert task["metadata"]["company"] == "Acme Corp"
        assert task["metadata"]["phase"] == "intel"
        assert task["metadata"]["file_path"] == "/tmp/dossier/acme/intel.md"
