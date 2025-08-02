import asyncio
from datetime import datetime, timedelta
import os
import time
import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics
from rustic_ai.core.agents.planners.todo_agent import (
    AddTaskRequest,
    DeleteTaskRequest,
    GetTaskRequest,
    NextTaskRequest,
    TODOAgent,
    UpdateTaskRequest,
    ListTasksRequest,
    ListTasksResponse
)
from rustic_ai.core.agents.system.models import UserAgentCreationRequest
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils import GemstoneGenerator, Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class TestTodoGuild:

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///test_todo_guild.db"

        if os.path.exists("test_todo_guild.db"):
            os.remove("test_todo_guild.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def todo_guild(self, rgdatabase):
        guild_builder = GuildBuilder(
            guild_id=f"todo_guild_{shortuuid.uuid()}",
            guild_name="TODO Guild",
            guild_description="Manage TODOs",
        )

        todo_agent = (
            AgentBuilder(TODOAgent)
            .set_id("todo_agent")
            .set_name("TODO Agent")
            .set_description("An agent for managing TODO tasks")
            .build_spec()
        )

        guild_builder.add_agent_spec(todo_agent)

        todo_guild = guild_builder.bootstrap(rgdatabase, "test_org")
        yield todo_guild
        todo_guild.shutdown()

    @pytest.mark.asyncio
    async def test_todo_flow(self, todo_guild: Guild):
        generator = GemstoneGenerator(17)
        probe_agent = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .build()
        )

        todo_guild._add_local_agent(probe_agent)

        # Create user
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        await asyncio.sleep(2)
        probe_agent.clear_messages()

        # Step 1: Add a task
        # task_id = generator.get_id(Priority.NORMAL)
        task_id = shortuuid.uuid()
        add_request = AddTaskRequest(
            id=task_id,
            todo="Write unit tests",
            start_time=datetime.now().isoformat(),
            deadline=(datetime.now() + timedelta(days=1)).isoformat(),
            depends_on=[]
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

        loop = 1
        while loop <= 100:
            results = probe_agent.get_messages()[-1]
            check = "GetTaskResponse" in results.format
            if check:
                break
            time.sleep(0.1)
            loop += 1

        get_task_response = probe_agent.get_messages()[-1]
        assert get_task_response.payload['task']['todo'] == 'Write unit tests'

        # Step 3: Update task
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

        await asyncio.sleep(10)

        # Step 4: Get next pending task
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

        loop = 1
        while loop <= 100:
            results = probe_agent.get_messages()[-1]
            check = "GetTaskResponse" in results.format
            if check:
                break
            time.sleep(0.1)
            loop += 1

        next_task_messages = probe_agent.get_messages()[-1]
        assert next_task_messages.payload['task']['todo'] == 'Write better unit tests'

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
        list_request = ListTasksRequest(status="pending")
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

        loop = 1
        while loop <= 100:
            results = probe_agent.get_messages()[-1]
            check = "ListTasksResponse" in results.format
            if check:
                break
            time.sleep(0.1)
            loop += 1

        list_reponse = probe_agent.get_messages()[-1]
        assert len(list_reponse.payload["tasks"]) == 0
