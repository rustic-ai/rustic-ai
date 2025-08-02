from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from rustic_ai.core import Agent, AgentMode, AgentType
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.state.models import StateUpdateFormat


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    todo: str
    start_time: datetime = Field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    depends_on: List[UUID] = []
    status: str = "pending"  # pending | in_progress | blocked | done | overdue

    @field_validator("deadline")
    @classmethod
    def deadline_after_start(cls, deadline_value, info):
        start_time = info.data.get("start_time")
        if start_time and deadline_value and deadline_value < start_time:
            raise ValueError("Deadline must be after start time.")
        return deadline_value


class AddTaskRequest(BaseModel):
    todo: str
    start_time: datetime
    deadline: Optional[datetime]
    depends_on: List[UUID]


class UpdateTaskRequest(BaseModel):
    id: UUID
    todo: Optional[str]
    start_time: Optional[datetime]
    deadline: Optional[datetime]
    depends_on: Optional[List[UUID]]


class DeleteTaskRequest(BaseModel):
    id: UUID


class GetTaskRequest(BaseModel):
    id: UUID


class ListTasksRequest(BaseModel):
    status: Optional[str] = None  # pending, done, etc.


class ListTasksResponse(BaseModel):
    tasks: List[Task]


class GetTaskResponse(BaseModel):
    task: Task


class UpdateStatusRequest(BaseModel):
    id: UUID
    status: str  # "done", "pending", "in_progress", "blocked", "overdue"


class TODOAgent(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(
            agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )

    def get_tasks(self) -> List[Task]:
        agent_state = self.get_agent_state()
        return [Task(**t) for t in agent_state.get("tasks", [])]

    def save_tasks(self, tasks: List[Task], ctx):
        self.update_state(
            ctx=ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={"tasks": [task.model_dump() for task in tasks]},
        )

    @agent.processor(AddTaskRequest)
    def add_task(self, ctx: ProcessContext[AddTaskRequest]):
        tasks = self.get_tasks()
        task_map = {t.id: t for t in tasks}

        # Determine initial status based on dependencies
        status = "pending"
        if ctx.payload.depends_on:
            for dep_id in ctx.payload.depends_on:
                if dep_id not in task_map or task_map[dep_id].status != "done":
                    status = "blocked"
                    break

        # Create the task with computed status
        task = Task(
            todo=ctx.payload.todo,
            start_time=ctx.payload.start_time,
            deadline=ctx.payload.deadline,
            depends_on=ctx.payload.depends_on,
            status=status,
        )

        tasks.append(task)
        self.save_tasks(tasks, ctx)

    @agent.processor(UpdateTaskRequest)
    def update_task(self, ctx: ProcessContext[UpdateTaskRequest]):
        tasks = self.get_tasks()
        for i, task in enumerate(tasks):
            if task.id == ctx.payload.id:
                updated_data = ctx.payload.model_dump(exclude_unset=True)
                updated_data.pop("id", None)
                updated_task = task.model_copy(update=updated_data)
                tasks[i] = updated_task
                self.save_tasks(tasks, ctx)

        raise ValueError("Task not found")

    @agent.processor(DeleteTaskRequest)
    def delete_task(self, ctx: ProcessContext[DeleteTaskRequest]):
        tasks = self.get_tasks()
        task_map = {t.id: t for t in tasks}
        deleted_id = ctx.payload.id

        # Step 1: Delete the task
        tasks = [t for t in tasks if t.id != deleted_id]

        # Step 2: Update dependent tasks
        for i, task in enumerate(tasks):
            if deleted_id in task.depends_on:
                task.depends_on = [dep for dep in task.depends_on if dep != deleted_id]

                # Check if all remaining dependencies are done
                if all(dep_id in task_map and task_map[dep_id].status == "done" for dep_id in task.depends_on):
                    task.status = "pending"

                tasks[i] = task

        self.save_tasks(tasks, ctx)

    @agent.processor(GetTaskRequest)
    def get_task(self, ctx: ProcessContext[GetTaskRequest]):
        tasks = self.get_tasks()
        for task in tasks:
            if task.id == ctx.payload.id:
                ctx.send(task=task)
                break

    @agent.processor(ListTasksRequest)
    def list_tasks(self, ctx: ProcessContext[ListTasksRequest]):
        tasks = self.get_tasks()
        status = ctx.payload.status
        if status:
            tasks = [t for t in tasks if t.status == status]

        ctx.send(ListTasksResponse(tasks=tasks))

    @agent.processor(UpdateStatusRequest)
    def update_status(self, ctx: ProcessContext[UpdateStatusRequest]):
        tasks = self.get_tasks()
        task_map = {t.id: t for t in tasks}
        updated = None

        for i, task in enumerate(tasks):
            if task.id == ctx.payload.id:
                task.status = ctx.payload.status
                tasks[i] = task
                updated = task
                break

        if not updated:
            raise ValueError("Task not found")

        # If task is marked as done, try unblocking other tasks
        if ctx.payload.status == "done":
            for i, task in enumerate(tasks):
                if ctx.payload.id in task.depends_on and task.status == "blocked":
                    # Check if all dependencies are done
                    all_done = all(
                        task_map.get(dep_id) and task_map[dep_id].status == "done" for dep_id in task.depends_on
                    )
                    if all_done:
                        task.status = "pending"
                        tasks[i] = task

        self.save_tasks(tasks, ctx)
