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
    TaskStatus,
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

    @pytest.mark.asyncio
    async def test_completion_with_result(self, todolist_guild: Guild):
        """Test that completing a task with result stores and returns the result."""
        generator = GemstoneGenerator(21)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_result")
            .set_name("Test Agent Result")
            .set_description("A test probe agent for result tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_result"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user_result", user_name="test_user_result").model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        task_id = "task-with-result"

        # Add task
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_result"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=task_id,
                    todo="Task to complete with result",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_result"),
            ),
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete task with result
        result_data = {"output": "analysis complete", "score": 0.95}
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_result"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=task_id, status=TaskStatus.DONE, result=result_data).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_result"),
            ),
        )

        # Wait for TaskCompletedEvent
        completed_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskCompletedEvent" in m.format,
        )
        assert completed_event.payload["task"]["result"] == result_data

        # Get task and verify result is persisted
        probe_agent.clear_messages()
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_result"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=GetTaskRequest(id=task_id).model_dump(),
                format=get_qualified_class_name(GetTaskRequest),
                sender=AgentTag(id="test_agent_result"),
            ),
        )

        get_response = await self.wait_for_message(
            probe_agent,
            lambda m: "GetTaskResponse" in m.format,
        )
        assert get_response.payload["task"]["result"] == result_data

    @pytest.mark.asyncio
    async def test_single_dependency_result_aggregation(self, todolist_guild: Guild):
        """Test that completing a dependency aggregates result into TaskUnblockedEvent."""
        generator = GemstoneGenerator(22)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_single_agg")
            .set_name("Test Agent Single Agg")
            .set_description("A test probe agent for single aggregation tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_single_agg"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(
                user_id="test_user_single_agg", user_name="test_user_single_agg"
            ).model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        child_id = "child-single"
        parent_id = "parent-single"
        child_result = {"intel": "gathered", "files": ["/a.md", "/b.md"]}

        # Add child task
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_single_agg"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=child_id,
                    todo="Child task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_single_agg"),
            ),
        )
        await asyncio.sleep(1)

        # Add parent task depending on child
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_single_agg"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=parent_id,
                    todo="Parent task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[child_id],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_single_agg"),
            ),
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete child with result
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_single_agg"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=child_id, status=TaskStatus.DONE, result=child_result).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_single_agg"),
            ),
        )

        # Wait for TaskUnblockedEvent with aggregated results
        unblocked_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskUnblockedEvent" in m.format,
        )
        assert unblocked_event.payload["task_id"] == parent_id
        assert unblocked_event.payload["dependency_results"][child_id] == child_result

    @pytest.mark.asyncio
    async def test_multiple_dependency_result_aggregation(self, todolist_guild: Guild):
        """Test that completing multiple dependencies aggregates all results."""
        generator = GemstoneGenerator(23)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_multi_agg")
            .set_name("Test Agent Multi Agg")
            .set_description("A test probe agent for multi aggregation tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_multi_agg"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(
                user_id="test_user_multi_agg", user_name="test_user_multi_agg"
            ).model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        child1_id = "child-multi-1"
        child2_id = "child-multi-2"
        child3_id = "child-multi-3"
        parent_id = "parent-multi"

        child1_result = {"source": "news", "count": 10}
        child2_result = {"source": "financial", "count": 5}
        child3_result = {"source": "social", "count": 20}

        # Add all child tasks
        for child_id in [child1_id, child2_id, child3_id]:
            probe_agent.publish(
                topic=UserProxyAgent.get_user_inbox_topic("test_user_multi_agg"),
                payload=Message(
                    id_obj=generator.get_id(Priority.NORMAL),
                    topics="default_topic",
                    payload=AddTaskRequest(
                        id=child_id,
                        todo=f"Child task {child_id}",
                        start_time=datetime.now().isoformat(),
                        depends_on=[],
                    ).model_dump(),
                    format=get_qualified_class_name(AddTaskRequest),
                    sender=AgentTag(id="test_agent_multi_agg"),
                ),
            )
            await asyncio.sleep(0.5)

        # Add parent task depending on all children
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_multi_agg"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=parent_id,
                    todo="Parent task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[child1_id, child2_id, child3_id],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_multi_agg"),
            ),
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete all children with results, waiting for each completion
        for child_id, result in [(child1_id, child1_result), (child2_id, child2_result), (child3_id, child3_result)]:
            probe_agent.publish(
                topic=UserProxyAgent.get_user_inbox_topic("test_user_multi_agg"),
                payload=Message(
                    id_obj=generator.get_id(Priority.NORMAL),
                    topics="default_topic",
                    payload=UpdateStatusRequest(id=child_id, status=TaskStatus.DONE, result=result).model_dump(),
                    format=get_qualified_class_name(UpdateStatusRequest),
                    sender=AgentTag(id="test_agent_multi_agg"),
                ),
            )
            # Wait for TaskCompletedEvent to ensure result is persisted before next completion
            await self.wait_for_message(
                probe_agent,
                lambda m, cid=child_id: "TaskCompletedEvent" in m.format and m.payload.get("task_id") == cid,
            )

        # Wait for TaskUnblockedEvent with all aggregated results
        unblocked_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskUnblockedEvent" in m.format,
        )
        assert unblocked_event.payload["task_id"] == parent_id
        assert unblocked_event.payload["dependency_results"][child1_id] == child1_result
        assert unblocked_event.payload["dependency_results"][child2_id] == child2_result
        assert unblocked_event.payload["dependency_results"][child3_id] == child3_result

    @pytest.mark.asyncio
    async def test_partial_results_aggregation(self, todolist_guild: Guild):
        """Test that only dependencies with results are included in aggregation."""
        generator = GemstoneGenerator(24)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_partial")
            .set_name("Test Agent Partial")
            .set_description("A test probe agent for partial results tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_partial"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(
                user_id="test_user_partial", user_name="test_user_partial"
            ).model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        child_with_result_id = "child-with-result"
        child_no_result_id = "child-no-result"
        parent_id = "parent-partial"
        child_result = {"data": "some result"}

        # Add both child tasks
        for child_id in [child_with_result_id, child_no_result_id]:
            probe_agent.publish(
                topic=UserProxyAgent.get_user_inbox_topic("test_user_partial"),
                payload=Message(
                    id_obj=generator.get_id(Priority.NORMAL),
                    topics="default_topic",
                    payload=AddTaskRequest(
                        id=child_id,
                        todo=f"Child task {child_id}",
                        start_time=datetime.now().isoformat(),
                        depends_on=[],
                    ).model_dump(),
                    format=get_qualified_class_name(AddTaskRequest),
                    sender=AgentTag(id="test_agent_partial"),
                ),
            )
            await asyncio.sleep(0.5)

        # Add parent task depending on both children
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_partial"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=parent_id,
                    todo="Parent task",
                    start_time=datetime.now().isoformat(),
                    depends_on=[child_with_result_id, child_no_result_id],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_partial"),
            ),
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete first child WITH result
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_partial"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(
                    id=child_with_result_id, status=TaskStatus.DONE, result=child_result
                ).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_partial"),
            ),
        )

        # Wait for TaskCompletedEvent to ensure result is persisted
        await self.wait_for_message(
            probe_agent,
            lambda m: "TaskCompletedEvent" in m.format and m.payload.get("task_id") == child_with_result_id,
        )
        probe_agent.clear_messages()

        # Complete second child WITHOUT result
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_partial"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=child_no_result_id, status=TaskStatus.DONE).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_partial"),
            ),
        )

        # Wait for TaskUnblockedEvent
        unblocked_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskUnblockedEvent" in m.format,
        )
        assert unblocked_event.payload["task_id"] == parent_id
        # Only the child with result should be in dependency_results
        assert child_with_result_id in unblocked_event.payload["dependency_results"]
        assert unblocked_event.payload["dependency_results"][child_with_result_id] == child_result
        assert child_no_result_id not in unblocked_event.payload["dependency_results"]

    @pytest.mark.asyncio
    async def test_complex_jsondict_result(self, todolist_guild: Guild):
        """Test that complex nested JsonDict results are serialized correctly."""
        generator = GemstoneGenerator(25)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent_complex")
            .set_name("Test Agent Complex")
            .set_description("A test probe agent for complex result tests")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(UserProxyAgent.get_user_notifications_topic("test_user_complex"))
            .build_spec()
        )

        probe_agent: ProbeAgent = todolist_guild._add_local_agent(probe_spec)  # type: ignore

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(
                user_id="test_user_complex", user_name="test_user_complex"
            ).model_dump(),
            format=UserAgentCreationRequest,
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        task_id = "task-complex-result"
        complex_result = {
            "metrics": {
                "score": 0.95,
                "confidence": 0.87,
                "breakdown": {"precision": 0.92, "recall": 0.98},
            },
            "files": ["/tmp/output/a.md", "/tmp/output/b.md", "/tmp/output/c.md"],
            "nested_list": [[1, 2, 3], [4, 5, 6]],
            "nullable_field": None,
            "boolean_field": True,
            "integer_field": 42,
        }

        # Add task
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_complex"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=AddTaskRequest(
                    id=task_id,
                    todo="Task with complex result",
                    start_time=datetime.now().isoformat(),
                    depends_on=[],
                ).model_dump(),
                format=get_qualified_class_name(AddTaskRequest),
                sender=AgentTag(id="test_agent_complex"),
            ),
        )
        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Complete task with complex result
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user_complex"),
            payload=Message(
                id_obj=generator.get_id(Priority.NORMAL),
                topics="default_topic",
                payload=UpdateStatusRequest(id=task_id, status=TaskStatus.DONE, result=complex_result).model_dump(),
                format=get_qualified_class_name(UpdateStatusRequest),
                sender=AgentTag(id="test_agent_complex"),
            ),
        )

        # Wait for TaskCompletedEvent
        completed_event = await self.wait_for_message(
            probe_agent,
            lambda m: "TaskCompletedEvent" in m.format,
        )

        # Verify complex structure is preserved
        result = completed_event.payload["task"]["result"]
        assert result["metrics"]["score"] == 0.95
        assert result["metrics"]["breakdown"]["precision"] == 0.92
        assert result["files"] == ["/tmp/output/a.md", "/tmp/output/b.md", "/tmp/output/c.md"]
        assert result["nested_list"] == [[1, 2, 3], [4, 5, 6]]
        assert result["nullable_field"] is None
        assert result["boolean_field"] is True
        assert result["integer_field"] == 42
