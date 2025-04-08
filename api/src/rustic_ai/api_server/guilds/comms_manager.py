import asyncio
import logging
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

import shortuuid
from fastapi import WebSocket, WebSocketDisconnect
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import Engine

from rustic_ai.core.agents.system.guild_manager_agent import UserAgentCreationRequest
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.agent_ext.mixins.telemetry import TelemetryConstants
from rustic_ai.core.guild.builders import GuildHelper
from rustic_ai.core.guild.dsl import GuildSpec, GuildTopics
from rustic_ai.core.guild.metastore.guild_store import GuildStore
from rustic_ai.core.messaging.client.message_tracking_client import (
    MessageTrackingClient,
)
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.messaging.core.messaging_interface import MessagingInterface
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class GuildCommunicationManager:
    _gemstone: GemstoneGenerator = GemstoneGenerator(random.randint(10, 100))
    _instance: Optional["GuildCommunicationManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.websockets: Dict[Tuple[str, str], List[WebSocket]] = {}
            self.initialized = True
            self.tracer = trace.get_tracer(TelemetryConstants.TRACER_NAME)
            self.guild_specs: Dict[str, GuildSpec] = {}
            self.messaging_interfaces: Dict[str, MessagingInterface] = {}

    async def shutdown(self):
        for _, messaging in self.messaging_interfaces.items():
            messaging.shutdown()

    async def get_or_fetch_guild_spec(self, guild_id: str, engine: Engine) -> Optional[GuildSpec]:
        if guild_id not in self.guild_specs:
            guild_store = GuildStore(engine)
            guild_model = guild_store.get_guild(guild_id)

            if guild_model:
                self.guild_specs[guild_id] = guild_model.to_guild_spec()
            else:  # pragma: no cover
                logging.debug(f"Guild with ID {guild_id} not found")
                return None

        return self.guild_specs[guild_id]

    async def get_or_create_messaging_interface(self, guild_spec: GuildSpec) -> MessagingInterface:
        guild_id = guild_spec.id
        if guild_id not in self.messaging_interfaces:
            guild_spec = guild_spec
            messaging_config = GuildHelper.get_messaging_config(guild_spec)
            self.messaging_interfaces[guild_id] = MessagingInterface(guild_id, messaging_config)
        return self.messaging_interfaces[guild_id]

    async def create_guild_client(
        self,
        guild_id: str,
        user_id: str,
        messaging: MessagingInterface,
        websocket: WebSocket,
        loop: asyncio.AbstractEventLoop,
    ) -> Client:
        uuid = shortuuid.uuid()
        client = MessageTrackingClient(
            uuid, f"{guild_id}_{uuid}", self.build_message_handler(guild_id, user_id, websocket, loop)
        )
        messaging.register_client(client)
        return client

    def build_message_handler(
        self,
        guild_id: str,
        user_id: str,
        websocket: WebSocket,
        loop: asyncio.AbstractEventLoop,
    ) -> Callable[[Message], None]:
        def on_message(message: Message) -> None:
            logging.debug(f"Received message: {message}")

            try:
                coroutine = self.send_message(guild_id, user_id, message, websocket)
                asyncio.run_coroutine_threadsafe(coroutine, loop)
            except ValueError as e:  # pragma: no cover
                logging.error(f"Invalid message received: {e}")
            except RuntimeError as e:  # pragma: no cover
                logging.error(f"Error sending message: {e}")
            except Exception as e:  # pragma: no cover
                logging.error(f"Error sending message: {e}")

        return on_message

    async def send_message(self, guild_id: str, user_id: str, message: Message, websocket: WebSocket):
        logging.debug(f"Sending message to User[{user_id}] on WS[{websocket}]: \n{message.model_dump_json()}")
        span_context = None
        if message.traceparent:
            carrier = {"traceparent": message.traceparent}
            span_context = TraceContextTextMapPropagator().extract(carrier)
        with self.tracer.start_as_current_span(
            "websocket:send_message",
            attributes={
                "user_id": user_id,
                "guild_id": guild_id,
                "message_id": f"id:{message.id}",
                "message_format": message.format,
                "message_topic": message.topic_published_to or "UNKNOWN",
                "agent_id": message.sender.id or "UNKNOWN",
                "agent_name": message.sender.name or "UNKNOWN",
                "root_thread_id": f"id:{message.root_thread_id}",
            },
            context=span_context,
        ):
            try:
                await websocket.send_json(message.model_dump())
            except Exception as e:  # pragma: no cover
                logging.error(f"Error sending message: {e}")

    async def handle_websocket_connection(
        self,
        websocket: WebSocket,
        guild_id: str,
        user_id: str,
        user_name: str,
        engine: Engine,
    ):
        guild_spec = await self.get_or_fetch_guild_spec(guild_id, engine)

        if not guild_spec:  # pragma: no cover
            logging.error(f"Guild with ID {guild_id} not found")
            await websocket.close()
            return
        else:
            await websocket.accept()

            loop = asyncio.get_running_loop()

            messaging: MessagingInterface = await self.get_or_create_messaging_interface(guild_spec)
            guild_client: Client = await self.create_guild_client(guild_id, user_id, messaging, websocket, loop)
            messaging.subscribe(UserProxyAgent.get_user_notifications_topic(user_id), guild_client)

            user_agent_tag = AgentTag(id=f"user_socket:{user_id}", name=user_name)

            guild_client.publish(
                Message(
                    self._gemstone.get_id(Priority.NORMAL),
                    topics=GuildTopics.SYSTEM_TOPIC,
                    sender=user_agent_tag,
                    format=get_qualified_class_name(UserAgentCreationRequest),
                    payload=UserAgentCreationRequest(user_id=user_id, user_name=user_name).model_dump(),
                )
            )

            try:
                while True:
                    try:
                        data = await websocket.receive_json()
                    except ValueError as e:  # pragma: no cover
                        logging.error(f"Invalid JSON received: {e}")
                        continue

                    id = data.get("id", None)

                    if id and isinstance(id, str):
                        idg = self._gemstone.get_id_from_string(id)
                    elif id and isinstance(id, int):
                        idg = self._gemstone.get_id_from_int(id)

                    priority = Priority(data.get("priority", Priority.NORMAL.value))
                    if not idg or idg.timestamp - (time.time_ns() // 1000000) > 1000:  # pragma: no cover
                        data["id"] = self._gemstone.get_id(priority).to_int()
                    else:
                        data["id"] = idg.to_int()

                    with self.tracer.start_as_current_span(
                        "websocket:receive_message",
                        attributes={
                            "user_id": user_id,
                            "guild_id": guild_id,
                            "guild_name": guild_spec.name,
                            "message_id": f"id:{data['id']}",
                            "message_format": data.get("format", "UNKNOWN"),
                        },
                    ) as span:

                        carrier: Dict[str, str] = {}
                        TraceContextTextMapPropagator().inject(carrier, context=trace.set_span_in_context(span))

                        logging.debug(f"Carrier: {carrier}")

                        data["sender"] = user_agent_tag.model_dump()

                        if "thread" not in data or not data["thread"]:
                            data["thread"] = []

                        traceparent = carrier.get("traceparent", TelemetryConstants.NO_TRACING)

                        data["thread"].append(data["id"])
                        data["traceparent"] = traceparent

                        try:
                            logging.debug(f"Received message: {data}")
                            message = Message(
                                idg,
                                topics=UserProxyAgent.get_user_inbox_topic(user_id),
                                sender=user_agent_tag,
                                format=get_qualified_class_name(Message),
                                payload=data,
                                thread=[data["id"]],
                                traceparent=traceparent,
                            )

                            logging.debug(f"Publishing message: {message.model_dump_json()}")

                            if message:
                                guild_client.publish(message)

                        except ValueError as e:  # pragma: no cover
                            logging.error(f"Invalid message received: {e}")
                            continue

            except WebSocketDisconnect:
                messaging.unsubscribe(UserProxyAgent.get_user_notifications_topic(user_id), guild_client)

    async def get_historical_user_notifications(self, guild_id: str, user_id: str, engine: Engine) -> List[Message]:
        guild_spec = await self.get_or_fetch_guild_spec(guild_id, engine)

        logging.debug(f"Retrieving historical messages for User[{user_id}] in Guild[{guild_id}]")

        if guild_spec:
            mi = await self.get_or_create_messaging_interface(guild_spec)
            msgs = mi.get_messages(UserProxyAgent.get_user_notifications_topic(user_id))
            logging.debug(f"Retrieved {len(msgs)} messages")
            return msgs
        else:  # pragma: no cover
            return []

    @classmethod
    def get_instance(cls) -> "GuildCommunicationManager":
        gcm = GuildCommunicationManager()
        return gcm
