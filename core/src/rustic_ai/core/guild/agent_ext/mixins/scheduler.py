from datetime import datetime, timedelta
import logging
from typing import Dict

from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.utils import JsonDict

log = logging.getLogger(__name__)


class ScheduleOnceMessage(BaseModel):
    key: str = Field(default_factory=shortuuid.uuid)
    delay_seconds: float
    mesage_payload: JsonDict
    message_format: str


class ScheduleFixedRateMessage(BaseModel):
    key: str = Field(default_factory=shortuuid.uuid)
    interval_seconds: float
    mesage_payload: JsonDict
    message_format: str


class CancelScheduledJobMessage(BaseModel):
    key: str


class SchedulerMixin:
    """
    Robust SchedulerMixin using APScheduler BackgroundScheduler.
    Jobs run on a background thread; when fired they submit the agent coroutine
    `_send_to_self(message)` into the agent's running asyncio loop.
    """

    def _init_scheduler(self):
        """Initialize internal bookkeeping (no scheduler thread started)."""
        self._scheduler = None  # BackgroundScheduler instance (threaded) once created
        self._scheduled_jobs: Dict[str, str] = {}  # key -> job id
        self._scheduler_started = False

    def _ensure_init(self):
        """Make sure internal fields exist (safe if __init__ of mixin isn't called)."""
        if not hasattr(self, "_scheduled_jobs"):
            self._init_scheduler()

    def _start_background_scheduler(self):
        """Start BackgroundScheduler once (idempotent)."""
        self._ensure_init()
        if self._scheduler is None:
            self._scheduler = BackgroundScheduler()

        if not self._scheduler_started:
            self._scheduler.start()
            self._scheduler_started = True
            log.info("SchedulerMixin: BackgroundScheduler started")

    def _job_wrapper(self, format_str: str, payload: dict):
        """
        Runs inside BackgroundScheduler worker thread.
        Construct the message object and submit _send_dict_to_self coroutine to agent loop.
        """
        self._send_dict_to_self(payload=payload, format=format_str)  # type: ignore

    def schedule_once(self, key: str, delay_seconds: float, payload: JsonDict, format: str):
        """
        Schedule a one-time message to self after `delay_seconds`.
        Must be called from agent code (i.e. inside the agent's event loop).
        """
        self._ensure_init()

        # start scheduler thread if needed
        self._start_background_scheduler()

        # remove previous job with same key
        self.cancel_timer(key)

        run_time = datetime.now() + timedelta(seconds=delay_seconds)

        if not self._scheduler:
            raise Exception("Scheduler not initialized!")

        # add job that calls job_wrapper in background thread
        job = self._scheduler.add_job(
            func=self._job_wrapper,
            trigger="date",
            run_date=run_time,
            args=[format, payload],
            id=key,
            replace_existing=True,
        )

        self._scheduled_jobs[key] = job.id
        log.info("[SchedulerMixin] Scheduled one-time timer '%s' for %s", key, run_time.isoformat())

    def schedule_fixed_rate(self, key: str, interval_seconds: float, payload: JsonDict, format: str):
        """
        Schedule recurring job. Also runs job_wrapper so messages are created and submitted to agent loop.
        """
        self._ensure_init()

        self._start_background_scheduler()
        self.cancel_timer(key)

        if not self._scheduler:
            raise Exception("Scheduler not initialized!")

        job = self._scheduler.add_job(
            func=self._job_wrapper,
            trigger="interval",
            seconds=interval_seconds,
            args=[format, payload],
            id=key,
            replace_existing=True,
        )

        self._scheduled_jobs[key] = job.id
        log.info("[SchedulerMixin] Scheduled fixed-rate timer '%s' every %ss", key, interval_seconds)

    def cancel_timer(self, key: str):
        self._ensure_init()
        job_id = self._scheduled_jobs.pop(key, None)
        if job_id and self._scheduler and self._scheduler.get_job(job_id):
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                log.exception("SchedulerMixin: failed to remove job %s", key)
            else:
                log.info("SchedulerMixin: cancelled timer '%s'", key)

    def cancel_all_timers(self):
        self._ensure_init()
        for k in list(self._scheduled_jobs.keys()):
            self.cancel_timer(k)

    def shutdown_scheduler(self):
        self._ensure_init()
        if self._scheduler and self._scheduler_started:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                log.exception("SchedulerMixin: error shutting down scheduler")
            finally:
                self._scheduler_started = False
                self._scheduler = None
                self._scheduled_jobs.clear()
                log.info("SchedulerMixin: scheduler shut down")

    # Hook processors
    @processor(ScheduleOnceMessage)
    def schedule_once_on_message(self, ctx: ProcessContext[ScheduleOnceMessage]):
        try:
            request = ctx.payload
            self.schedule_once(
                key=request.key,
                delay_seconds=request.delay_seconds,
                payload=request.mesage_payload,
                format=request.message_format,
            )
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),  # type: ignore
                    error_type="SchedulerError",
                    error_message=str(ex),
                )
            )

    @processor(ScheduleFixedRateMessage)
    def schedule_fixed_rate_on_message(self, ctx: ProcessContext[ScheduleFixedRateMessage]):
        try:
            request = ctx.payload
            self.schedule_fixed_rate(
                key=request.key,
                interval_seconds=request.interval_seconds,
                payload=request.mesage_payload,
                format=request.message_format,
            )
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),  # type: ignore
                    error_type="SchedulerError",
                    error_message=str(ex),
                )
            )

    @processor(CancelScheduledJobMessage)
    def cancel_on_message(self, ctx: ProcessContext[CancelScheduledJobMessage]):
        try:
            request = ctx.payload
            self.cancel_timer(key=request.key)
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),  # type: ignore
                    error_type="SchedulerError",
                    error_message=str(ex),
                )
            )
