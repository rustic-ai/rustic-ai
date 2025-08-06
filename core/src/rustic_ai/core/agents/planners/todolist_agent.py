from datetime import datetime
from enum import StrEnum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.state.models import StateUpdateFormat


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    OVERDUE = "overdue"
    ALL = "all"


class Task(BaseModel):
    id: str = Field(default=str(uuid4()))
    todo: str
    start_time: str = Field(default=datetime.now().isoformat())
    deadline: Optional[str] = None
    depends_on: List[str] = []
    status: TaskStatus = TaskStatus.PENDING  # pending | in_progress | blocked | done | overdue

    @field_validator("deadline")
    @classmethod
    def deadline_after_start(cls, deadline_value, info):
        start_time = info.data.get("start_time")
        if (
            start_time
            and deadline_value
            and datetime.fromisoformat(deadline_value) < datetime.fromisoformat(start_time)
        ):
            raise ValueError("Deadline must be after start time.")
        return deadline_value


class AddTaskRequest(BaseModel):
    id: str
    todo: str
    start_time: str
    deadline: Optional[str] = Field(default=None)
    depends_on: List[str]


class UpdateTaskRequest(BaseModel):
    id: str
    todo: Optional[str]
    start_time: Optional[str] = Field(default=None)
    deadline: Optional[str] = Field(default=None)
    depends_on: Optional[List[str]] = Field(default=None)


class DeleteTaskRequest(BaseModel):
    id: str


class GetTaskRequest(BaseModel):
    id: str


class ListTasksRequest(BaseModel):
    status: Optional[TaskStatus] = Field(default=None)  # all, pending, done, etc.


class ListTasksResponse(BaseModel):
    tasks: List[Task]


class GetTaskResponse(BaseModel):
    task: Task


class UpdateStatusRequest(BaseModel):
    id: str
    status: TaskStatus  # "done", "pending", "in_progress", "blocked", "overdue"


class NextTaskRequest(BaseModel):
    sort_by: Optional[str] = Field(default="start_time")  # can be start_time or deadline


class TodoListAgent(Agent):
    def get_tasks(self) -> List[Task]:
        agent_state = self.get_agent_state()
        if not agent_state:
            return []
        tasks: list = agent_state.get("tasks", [])  # type: ignore
        return [Task.model_validate(t) for t in tasks]

    def save_tasks(self, tasks: List[Task], ctx):
        self.update_state(  # type: ignore
            ctx=ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={"tasks": [task.model_dump() for task in tasks]},
        )

    @agent.processor(AddTaskRequest)
    def add_task(self, ctx: ProcessContext[AddTaskRequest]):
        tasks = self.get_tasks()
        task_map = {t.id: t for t in tasks}

        # Determine initial status based on dependencies
        status = TaskStatus.PENDING
        if ctx.payload.depends_on:
            for dep_id in ctx.payload.depends_on:
                if dep_id not in task_map or task_map[dep_id].status != TaskStatus.DONE:
                    status = TaskStatus.BLOCKED
                    break

        # Create the task with computed status
        task = Task(
            id=ctx.payload.id,
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
                # Only include fields that were provided AND not None
                updated_data = {
                    k: v for k, v in ctx.payload.model_dump(exclude_unset=True).items() if k != "id" and v is not None
                }
                updated_task = task.model_copy(update=updated_data)
                tasks[i] = updated_task
                self.save_tasks(tasks, ctx)
                return  # Exit once updated

        raise ValueError("Task not found")

    @agent.processor(DeleteTaskRequest)
    def delete_task(self, ctx: ProcessContext[DeleteTaskRequest]):
        tasks = self.get_tasks()
        deleted_id = ctx.payload.id

        # Step 1: Delete the task
        tasks = [t for t in tasks if t.id != deleted_id]

        # Step 2: Update dependent tasks
        for i, task in enumerate(tasks):
            if deleted_id in task.depends_on:
                task.depends_on = [dep for dep in task.depends_on if dep != deleted_id]

                if not task.depends_on:
                    task.status = TaskStatus.PENDING

                tasks[i] = task

        self.save_tasks(tasks, ctx)

    @agent.processor(GetTaskRequest)
    def get_task(self, ctx: ProcessContext[GetTaskRequest]):
        tasks = self.get_tasks()
        for task in tasks:
            if task.id == ctx.payload.id:
                ctx.send(GetTaskResponse(task=task))
                break

    @agent.processor(ListTasksRequest)
    def list_tasks(self, ctx: ProcessContext[ListTasksRequest]):
        tasks = self.get_tasks()
        status = ctx.payload.status
        if status != "all":
            tasks = [t for t in tasks if t.status == status]

        ctx.send(ListTasksResponse(tasks=tasks))

    @agent.processor(UpdateStatusRequest)
    def update_status(self, ctx: ProcessContext[UpdateStatusRequest]):
        tasks = self.get_tasks()
        updated = None

        for i, task in enumerate(tasks):
            if task.id == ctx.payload.id:
                task.status = ctx.payload.status
                tasks[i] = task
                updated = task
                break

        if not updated:
            raise ValueError("Task not found")

        if ctx.payload.status == TaskStatus.DONE:
            for task in tasks:
                if ctx.payload.id in task.depends_on and task.status == TaskStatus.BLOCKED:
                    task.depends_on.remove(ctx.payload.id)

                    # If no more dependencies left, mark as pending
                    if not task.depends_on:
                        task.status = TaskStatus.PENDING

        self.save_tasks(tasks, ctx)

    @agent.processor(NextTaskRequest)
    def get_next_task(self, ctx: ProcessContext[NextTaskRequest]):
        tasks = self.get_tasks()
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        if not pending_tasks:
            return None

        # Return the one with the earliest start_time
        if ctx.payload.sort_by == "start_time":
            next_task = min(pending_tasks, key=lambda t: datetime.fromisoformat(t.start_time))
        elif ctx.payload.sort_by == "deadline":
            next_task = min(
                pending_tasks, key=lambda t: datetime.fromisoformat(t.deadline) if t.deadline else datetime.max
            )
        else:
            raise KeyError("Sortby can be start_time or deadline only.")

        ctx.send(GetTaskResponse(task=next_task))
