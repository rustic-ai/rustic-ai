from abc import ABC, abstractmethod
import asyncio
import logging
import threading
from typing import Any, Dict, Optional, Type

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.utils import (
    build_agent_from_spec,
    subscribe_agent_with_messaging,
)
from rustic_ai.core.messaging import (
    Client,
    MessagingConfig,
    MessagingInterface,
    SimpleClient,
)
from rustic_ai.core.utils.class_utils import get_agent_class


class AgentWrapper(ABC):
    """
    Abstract base class for agent wrappers that handles common initialization logic for agents and their connection to the Messaging Interface.
    """

    def __init__(
        self,
        guild_spec: GuildSpec,
        agent_spec: AgentSpec,
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = SimpleClient,
        client_properties: Dict[str, Any] = {},
        organization_id: Optional[str] = None,
    ):
        """
        Initializes a new instance of the AgentWrapper class.

        Args:
            guild_spec: The spec for the guild this agent is being launched in.
            agent_spec: The agent specification or instance to wrap.
                NOTE: Providing an Agent is only supported for testing and should not be used in production.
            messaging_config: The messaging configuration to use for the agent.
            machine_id: A unique identifier for the machine generating the ID.
            client_type: The type of client to use for the agent.
            client_properties: Properties to initialize the client with.
            dependencies: A dictionary of dependencies for the agent.
        """
        # Create a named logger for this class
        self.logger = logging.getLogger(f"{guild_spec.id}.{guild_spec.name}.{agent_spec.name}")

        self._shutdown_lock = threading.RLock()
        self._shutdown_complete = False
        self._shutdown_started = False
        self._shutdown_running = False
        self._shutdown_task: asyncio.Task | None = None
        self._shutdown_thread: threading.Thread | None = None
        self._pending_resolvers: list[DependencyResolver] = []
        self.agent: Optional[Agent] = None

        self.agent_spec = agent_spec

        self.guild_spec = guild_spec
        self.messaging_config = messaging_config
        self.machine_id = machine_id
        self.client_type = client_type
        self.client_properties = client_properties
        self.messaging: MessagingInterface
        self.messaging_owned = False
        self.dependencies = guild_spec.dependency_map | self.agent_spec.dependency_map
        self.only_agent_class_name = self.agent_spec.class_name.split(".")[-1]
        self.organization_id = organization_id

    def __getstate__(self):
        # Wrappers cross process/distributed execution boundaries before launch.
        state = self.__dict__.copy()
        state.pop("_shutdown_lock", None)
        state.pop("_shutdown_thread", None)
        state.pop("_shutdown_task", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._shutdown_lock = threading.RLock()
        self._shutdown_task = None
        self._shutdown_thread = None

    def initialize_agent(self) -> Agent:
        with self._shutdown_lock:
            if self._shutdown_started or self._shutdown_complete:
                raise RuntimeError("Cannot initialize a stopped agent wrapper")
            agent = self._initialize_agent()
        # Ready handlers may stop this wrapper from the coroutine bridge thread.
        # Resource setup is protected; message delivery must not hold its lock.
        if not self._shutdown_started:
            agent._notify_ready()
        return agent

    def _initialize_agent(self) -> Agent:
        """
        Common logic for initializing the agent with the Messaging and its client.
        """
        self.logger.info(
            f"Starting initialization of agent {self.agent_spec.name} from class {self.agent_spec.class_name}"
        )

        agent_class = get_agent_class(self.agent_spec.class_name)

        # Initialize the agent's dependencies
        self.logger.debug(f"Loading dependencies for agent {self.agent_spec.name}")
        agent_deps = agent_class.list_all_dependencies()

        self.logger.debug(f"Agent dependencies: {agent_deps}")

        # Initialize the Messaging
        self.logger.info(f"Initializing messaging from config: {self.messaging_config}")
        self.messaging = MessagingInterface(self.guild_spec.id, self.messaging_config)
        self.logger.debug(f"Messaging initialized: {self.messaging}")
        self.messaging_owned = True

        self.agent = build_agent_from_spec(
            agent_spec=self.agent_spec,
            guild_spec=self.guild_spec,
            dependencies=self.dependencies,
            client_class=self.client_type,
            client_props=self.client_properties.copy(),
            machine_id=self.machine_id,
            organization_id=self.organization_id,
        )

        subscribe_agent_with_messaging(self.agent, self.messaging, self.organization_id)

        # Notify the agent that it is ready to process messages
        self.logger.info(f"Agent {self.agent_spec.name} is ready to process messages")
        return self.agent

    def _load_dependency_resolver(self, name: str) -> DependencyResolver:
        """
        Loads the dependency resolver for the given name.

        Args:
            name (str): The name of the dependency resolver.

        Returns:
            DependencyResolver: The dependency resolver for the agent.
        """
        if name in self.dependencies:
            resolver = self.dependencies[name].to_resolver()
            resolver.set_dependency_specs(self.dependencies)
            return resolver
        else:  # pragma: no cover
            raise ValueError(f"Dependency {name} not found in agent dependencies.")

    @abstractmethod
    def run(self) -> Optional[Agent]:
        """
        Runs the agent. This method should be implemented by concrete subclasses to define specific execution logic.
        """
        pass  # pragma: no cover

    def _claim_shutdown(self) -> bool | None:
        with self._shutdown_lock:
            if self._shutdown_complete or self._shutdown_running:
                return None
            self._shutdown_running = True
            first_stop = not self._shutdown_started
            self._shutdown_started = True
            self._shutdown_task = None
            return first_stop

    def shutdown(self) -> None:
        """Stop ingress immediately and drain owned resources.

        A synchronous call on an event loop drains on a separate thread so
        accepted work can finish on that loop. This worker outlives temporary
        processor loops. Await shutdown_async() to wait for resource release.
        Failed cleanup remains retryable without repeating the agent hook.
        """
        first_stop = self._claim_shutdown()
        if first_stop is None:
            return
        try:
            if first_stop:
                self._prepare_shutdown()
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                self._finish_shutdown()
            else:
                if not self._pending_resolvers:
                    self._finish_shutdown()
                else:
                    self._shutdown_thread = threading.Thread(target=self._finish_shutdown, daemon=False)
                    self._shutdown_thread.start()
        except BaseException:
            with self._shutdown_lock:
                self._shutdown_running = False
            raise

    async def shutdown_async(self) -> None:
        """Wait for owned cleanup, leaving failed obligations available to retry."""
        first_stop = self._claim_shutdown()
        if first_stop is not None:
            try:
                if first_stop:
                    self._prepare_shutdown()
                self._shutdown_task = asyncio.create_task(self._finish_shutdown_async())
            except BaseException:
                with self._shutdown_lock:
                    self._shutdown_running = False
                raise
        task = self._shutdown_task
        if task is not None:
            await asyncio.shield(task)
        else:
            while self._shutdown_running:
                await asyncio.sleep(0.005)

    def _prepare_shutdown(self) -> None:
        seen: set[int] = set()

        def collect(resolver):
            if id(resolver) in seen:
                return
            seen.add(id(resolver))
            self._pending_resolvers.append(resolver)
            for child in tuple(getattr(resolver, "_injectors", {}).values()):
                collect(child)

        for resolver in getattr(self.agent, "_owned_dependency_resolvers", ()):
            collect(resolver)
        messaging = getattr(self, "messaging", None)
        if self.agent is not None:
            if messaging is not None:
                for topic in self.agent.subscribed_topics:
                    try:
                        messaging.unsubscribe(topic, self.agent._get_client())
                    except Exception:
                        self.logger.exception("Failed to unsubscribe topic %s during shutdown", topic)
            try:
                self.agent.on_shutdown()
            except Exception:
                self.logger.exception("Agent shutdown hook failed")

    def _disconnect(self) -> None:
        messaging = getattr(self, "messaging", None)
        if messaging is not None:
            try:
                if self.agent is not None:
                    messaging.unregister_client(self.agent._get_client())
            finally:
                if self.messaging_owned:
                    messaging.shutdown()
        self._shutdown_complete = True

    def _finish_shutdown(self) -> None:
        try:
            for resolver in tuple(self._pending_resolvers):
                try:
                    resolver.shutdown()
                except Exception:
                    self.logger.exception("Dependency shutdown failed: %s", type(resolver).__name__)
                else:
                    self._pending_resolvers.remove(resolver)
            if not self._pending_resolvers:
                self._disconnect()
        finally:
            with self._shutdown_lock:
                self._shutdown_running = False

    async def _finish_shutdown_async(self) -> None:
        try:
            for resolver in tuple(self._pending_resolvers):
                try:
                    close_async = getattr(resolver, "shutdown_async", None)
                    if close_async is not None:
                        await close_async()
                    else:
                        await asyncio.to_thread(resolver.shutdown)
                except Exception:
                    self.logger.exception("Dependency shutdown failed: %s", type(resolver).__name__)
                else:
                    self._pending_resolvers.remove(resolver)
            if not self._pending_resolvers:
                self._disconnect()
        finally:
            with self._shutdown_lock:
                self._shutdown_running = False
