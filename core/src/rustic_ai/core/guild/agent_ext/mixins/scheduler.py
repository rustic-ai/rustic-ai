import asyncio
from datetime import datetime, timedelta
import logging
from typing import Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core.guild.agent import AgentFixtures, ProcessContext, processor
from rustic_ai.core.messaging.core.message import MDT
from rustic_ai.core.utils import JsonDict


class ScheduleOnceMessage(BaseModel):
    key: str = Field(default_factory=shortuuid.uuid)
    delay_seconds: float
    mesage_payload: JsonDict


class ScheduleFixedRateMessage(BaseModel):
    key: str = Field(default_factory=shortuuid.uuid)
    interval_seconds: float
    mesage_payload: JsonDict


class CancelScheduledJobMessage(BaseModel):
    key: str


class SchedulerMixin:
    """
    Mixin that enables scheduling messages to self for agents using APScheduler.
    Supports one-time, fixed-delay, and fixed-rate execution.
    """

    def _init_scheduler(self):
        self._scheduler = None
        self._scheduled_jobs: Dict[str, str] = {}
        self._scheduler_started = False

    @AgentFixtures.before_process
    def _ensure_scheduler(self, ctx: ProcessContext[MDT]):
        if not hasattr(self, "scheduler"):
            self._init_scheduler()
        if not self._scheduler_started:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            self._scheduler = AsyncIOScheduler(event_loop=loop)
            self._scheduler.start()
            self._scheduler_started = True

    def _ensure_scheduler_started(self):
        if not self._scheduler_started:
            self._scheduler.start()
            self._scheduler_started = True

    def schedule_once(self, key: str, delay_seconds: float, payload: JsonDict):
        """
        Schedule a one-time message to self after a delay.
        """
        self.cancel_timer(key)
        self._ensure_scheduler_started()

        run_time = datetime.now() + timedelta(seconds=delay_seconds)

        job = self._scheduler.add_job(
            func=self._send_to_self,
            trigger=DateTrigger(run_date=run_time),
            args=[payload],
            id=key,
            replace_existing=True,
        )
        self._scheduled_jobs[key] = job.id
        logging.info(f"[SchedulerMixin] Scheduled one-time timer '{key}' for {run_time.isoformat()}")

    def schedule_fixed_rate(self, key: str, interval_seconds: float, payload: BaseModel):
        """
        Schedule a recurring message to self at fixed intervals (compensates for delay).
        """
        self.cancel_timer(key)
        self._ensure_scheduler_started()

        job = self._scheduler.add_job(
            func=self._send_to_self,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[payload],
            id=key,
            replace_existing=True,
            coalesce=False,  # catch up missed runs
            misfire_grace_time=None,
        )
        self._scheduled_jobs[key] = job.id
        logging.info(f"[SchedulerMixin] Scheduled fixed-rate timer '{key}' every {interval_seconds}s")

    def cancel_timer(self, key: str):
        """
        Cancel a timer by key. Guarantees that stale jobs are removed.
        """
        job_id = self._scheduled_jobs.pop(key, None)
        if job_id and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logging.info(f"[SchedulerMixin] Cancelled timer '{key}'")

    def cancel_all_timers(self):
        """
        Cancel all active timers.
        """
        for key in list(self._scheduled_jobs):
            self.cancel_timer(key)
        logging.info("[SchedulerMixin] Cancelled all timers")

    def shutdown_scheduler(self):
        """
        Gracefully shut down the scheduler and clear jobs.
        """
        if self._scheduler_started:
            self._scheduler.shutdown(wait=False)
            self._scheduler_started = False
            self._scheduled_jobs.clear()
            logging.info("[SchedulerMixin] Scheduler shut down")

    @processor(ScheduleOnceMessage)
    def schedule_once_on_message(self, ctx: ProcessContext[ScheduleOnceMessage]):
        request = ctx.payload
        print("xxx schedule_once_on_message", request)
        self.schedule_once(key=request.key, delay_seconds=request.delay_seconds, payload=request.mesage_payload)

    @processor(ScheduleFixedRateMessage)
    def schedule_fixed_rate_on_message(self, ctx: ProcessContext[ScheduleFixedRateMessage]):
        request = ctx.payload
        self.schedule_fixed_rate(
            key=request.key, interval_seconds=request.interval_seconds, payload=request.mesage_payload
        )

    @processor(CancelScheduledJobMessage)
    def schedule_fixed_rate_on_message(self, ctx: ProcessContext[CancelScheduledJobMessage]):
        request = ctx.payload
        self.cancel_timer(key=request.key)
