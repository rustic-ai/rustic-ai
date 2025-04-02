import logging
from enum import StrEnum
from typing import Optional, cast

from opentelemetry import trace
from opentelemetry.trace import NoOpTracer, ProxyTracer, Span, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from rustic_ai.core.guild.agent import AgentFixtures, ProcessContext
from rustic_ai.core.messaging.core.message import MDT, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class TelemetryConstants(StrEnum):
    """
    Constants for Telemetry Mixin
    """

    NO_TRACING = "no_tracing"
    TRACER_NAME = "rustic_ai"
    PROCESS_SPAN_KEY = "otel_tracing_span"
    MESSAGE_SPAN_KEY = "otel_message_tracing_span"
    MESSAGE_TRACEPARENT = "message_traceparent"


OTEL_TRACER: Optional[trace.Tracer] = None


class TelemetryMixin:

    @staticmethod
    def _is_noop_tracer(tracer) -> bool:
        if isinstance(tracer, NoOpTracer):
            return True
        if isinstance(tracer, ProxyTracer):
            return TelemetryMixin._is_noop_tracer(tracer._tracer)
        return False

    @staticmethod
    def _get_tracer() -> trace.Tracer:
        global OTEL_TRACER
        if not OTEL_TRACER:
            OTEL_TRACER = trace.get_tracer(TelemetryConstants.TRACER_NAME)
        return OTEL_TRACER

    @AgentFixtures.before_process
    def setup_telemetry(self, ctx: ProcessContext[MDT]):
        tracer = TelemetryMixin._get_tracer()
        if TelemetryMixin._is_noop_tracer(tracer):
            setattr(ctx, TelemetryConstants.NO_TRACING, True)
            return
        else:
            logging.debug("Tracing is enabled for agent: [%s]", ctx.agent.name)
            span_context = None
            if ctx.message.traceparent:
                carrier = {"traceparent": ctx.message.traceparent}
                span_context = TraceContextTextMapPropagator().extract(carrier)

            with tracer.start_as_current_span(
                "rustic_ai:process_message",
                attributes={
                    "agent_name": ctx.agent.name,
                    "method_name": ctx.method_name,
                    "message_id": f"id:{ctx.message.id}",
                    "message_topic": ctx.message.topic_published_to or "UNKNOWN",
                    "message_sender": ctx.message.sender.model_dump_json(),
                    "message_format": ctx.message.format,
                    "agent_type": get_qualified_class_name(ctx.agent.__class__),
                    "root_thread_id": f"id:{ctx.message.root_thread_id}",
                    "current_thread_id": f"id:{ctx.message.current_thread_id}",
                    "agent_id": ctx.agent.id,
                    "guild_id": ctx.agent.guild_id,
                },
                context=span_context,
                end_on_exit=False,
            ) as span:
                setattr(ctx, TelemetryConstants.PROCESS_SPAN_KEY, span)
                if not ctx.message.traceparent:
                    carrier = {}
                    TraceContextTextMapPropagator().inject(carrier, trace.set_span_in_context(span))
                    ctx.message.traceparent = carrier.get("traceparent", TelemetryConstants.NO_TRACING)

    @AgentFixtures.on_send
    def on_send_tracing(self, ctx: ProcessContext[MDT]):
        if getattr(ctx, TelemetryConstants.NO_TRACING, False):
            return
        span: Span = TelemetryMixin._get_span(ctx)

        with TelemetryMixin._get_tracer().start_as_current_span(
            "rustic_ai:send_message",
            attributes={
                "agent_id": ctx.agent.id,
                "agent_name": ctx.agent.name,
                "agent_type": get_qualified_class_name(ctx.agent.__class__),
                "method_name": ctx.method_name,
                "origin_message_id": f"id:{ctx.message.id}",
                "root_thread_id": f"id:{ctx.message.root_thread_id}",
                "guild_id": ctx.agent.guild_id,
            },
            context=trace.set_span_in_context(span),
            end_on_exit=False,
        ) as messaging_span:
            setattr(ctx, TelemetryConstants.MESSAGE_SPAN_KEY, messaging_span)

            carrier: dict = {}
            TraceContextTextMapPropagator().inject(carrier, trace.set_span_in_context(span))

            setattr(
                ctx,
                TelemetryConstants.MESSAGE_TRACEPARENT,
                carrier.get("traceparent", TelemetryConstants.NO_TRACING),
            )

    @AgentFixtures.on_send_error
    def on_send_error_tracing(self, ctx: ProcessContext[MDT]):
        if getattr(ctx, TelemetryConstants.NO_TRACING, False):
            return
        span: Span = TelemetryMixin._get_span(ctx)

        with TelemetryMixin._get_tracer().start_as_current_span(
            "rustic_ai:send_error_message",
            attributes={
                "agent_id": ctx.agent.id,
                "agent_name": ctx.agent.name,
                "agent_type": get_qualified_class_name(ctx.agent.__class__),
                "method_name": ctx.method_name,
                "origin_message_id": f"id:{ctx.message.id}",
                "root_thread_id": f"id:{ctx.message.root_thread_id}",
                "guild_id": ctx.agent.guild_id,
            },
            context=trace.set_span_in_context(span),
            end_on_exit=False,
        ) as messaging_span:
            setattr(ctx, TelemetryConstants.MESSAGE_SPAN_KEY, messaging_span)

            carrier: dict = {}
            TraceContextTextMapPropagator().inject(carrier, trace.set_span_in_context(span))
            messaging_span.set_status(StatusCode.ERROR)

            setattr(
                ctx,
                TelemetryConstants.MESSAGE_TRACEPARENT,
                carrier.get("traceparent", TelemetryConstants.NO_TRACING),
            )

    @AgentFixtures.outgoing_message_modifier
    def enrich_message_with_tracing(self, ctx: ProcessContext[MDT], message: Message):
        if getattr(ctx, TelemetryConstants.NO_TRACING, False):
            return

        span: Span = TelemetryMixin._get_span(ctx, TelemetryConstants.MESSAGE_SPAN_KEY)
        current_routing_rule = ctx.current_routing_step

        assert current_routing_rule is not None

        span.set_attribute("message_format", message.format)
        span.set_attribute("message_topic", message.topic_published_to or "UNKNOWN")

        span.add_event(
            "sending_message",
            {
                "message_id": f"id:{message.id}",
            },
        )

        message.traceparent = getattr(ctx, TelemetryConstants.MESSAGE_TRACEPARENT, TelemetryConstants.NO_TRACING)

        if ctx.remaining_routing_steps == 1:  # Last routing step
            span.end()
            setattr(ctx, TelemetryConstants.MESSAGE_SPAN_KEY, None)
            setattr(ctx, TelemetryConstants.MESSAGE_TRACEPARENT, None)

    @AgentFixtures.after_process
    def teardown_telemetry(self, ctx: ProcessContext[MDT]):
        if getattr(ctx, TelemetryConstants.NO_TRACING, False):
            return

        span: Span = TelemetryMixin._get_span(ctx, TelemetryConstants.PROCESS_SPAN_KEY)
        if span:
            sent_message_ids = [f"id:{msg.id},topic:{msg.topics}" for msg in ctx.sent_messages]
            span.set_attribute("messages_sent", sent_message_ids)
            span.end()
            setattr(ctx, TelemetryConstants.PROCESS_SPAN_KEY, None)

    @classmethod
    def _get_span(
        cls,
        ctx: ProcessContext[MDT],
        span_key: str = TelemetryConstants.PROCESS_SPAN_KEY,
    ) -> Span:
        return cast(Span, getattr(ctx, span_key, None))
