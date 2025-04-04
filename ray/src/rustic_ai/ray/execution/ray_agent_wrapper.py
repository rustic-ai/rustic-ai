import logging
from typing import Any, Dict, Type, Union

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import ray
from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.agent_wrapper import AgentWrapper
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig


@ray.remote
class RayAgentWrapper(AgentWrapper):
    def __init__(
        self,
        guild_spec: GuildSpec,
        agent_spec: Union[AgentSpec, Agent],
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
    ):
        print("Setting up logging")
        logging_level = "INFO"
        handler = logging.StreamHandler()
        handler.setLevel(logging_level)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging_level)
        root_logger.addHandler(handler)

        ray_logger = logging.getLogger("ray")
        ray_logger.setLevel(logging_level)
        ray_logger.addHandler(handler)

        print("Setting up tracing")
        provider = TracerProvider()
        span_processor = SimpleSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(span_processor)
        trace.set_tracer_provider(provider)
        print("Tracing setup complete")

        super().__init__(guild_spec, agent_spec, messaging_config, machine_id, client_type, client_properties)

    def run(self) -> None:
        """
        Initializes the agent with Messaging and its client, then runs the agent asynchronously using Ray.
        """

        try:
            # Perform common initialization tasks
            # We skip coverage on this as it is run in a separate process and is not tracked by coverage
            logging.info(
                f"Initializing agent {self.agent_spec.name} from class {self.agent_spec.class_name}"
            )  # pragma: no cover
            logging.info(f"Agent properties: {self.agent_spec.properties}")
            logging.info(f"Agent client properties: {self.client_properties}")
            self.initialize_agent()  # pragma: no cover
            logging.info("Agent initialized")  # pragma: no cover

            self._is_running = True

        except Exception as e:
            logging.error(f"Error initializing agent {self.agent_spec.name}: {e}", exc_info=True)
            raise e

    def get_agent_spec(self):
        return self.agent_spec  # pragma: no cover

    def is_rustic_agent(self):
        return True

    def shutdown(self):
        self._is_running = False
        return super().shutdown()  # pragma: no cover

    def is_running(self):
        return self._is_running

    def __repr__(self):
        return f"[{self.only_agent_class_name} | {self.guild_spec.name} | {self.agent_spec.name}]"
