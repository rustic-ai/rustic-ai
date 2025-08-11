from datetime import datetime
import logging
from typing import List, Optional

from sqlmodel import Session

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.agents.system.guild_manager_agent_props import (
    GuildManagerAgentProps,
)
from rustic_ai.core.agents.system.models import (
    AgentGetRequest,
    AgentInfoResponse,
    AgentLaunchRequest,
    AgentLaunchResponse,
    AgentListRequest,
    AgentListResponse,
    BadInputResponse,
    ConflictResponse,
    GuildUpdatedAnnouncement,
    RunningAgentListRequest,
    StopGuildRequest,
    StopGuildResponse,
    UserAgentCreationRequest,
    UserAgentCreationResponse,
    UserAgentGetRequest,
)
from rustic_ai.core.agents.utils.user_proxy_agent import (
    UserProxyAgent,
    UserProxyAgentProps,
)
from rustic_ai.core.guild import (
    Agent,
    AgentSpec,
    GuildTopics,
    agent,
)
from rustic_ai.core.guild.agent import ProcessContext, SelfReadyNotification, processor
from rustic_ai.core.guild.agent_ext.mixins.health import (
    AgentsHealthReport,
    HealthCheckRequest,
    HealthConstants,
    Heartbeat,
    HeartbeatStatus,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, GuildHelper
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.guild.metastore import AgentModel, GuildModel, Metastore
from rustic_ai.core.guild.metastore.models import GuildStatus
from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.state.models import (
    StateFetchError,
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateError,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.class_utils import get_state_manager
from rustic_ai.core.utils.json_utils import JsonDict
from rustic_ai.core.utils.priority import Priority


class GuildManagerAgent(Agent[GuildManagerAgentProps]):
    def __init__(self):
        guild_spec = self.agent_spec.props.guild_spec
        database_url = self.agent_spec.props.database_url
        self.organization_id = self.agent_spec.properties.organization_id

        self.database_url = database_url
        self.engine = Metastore.get_engine(database_url)
        self.original_guild_spec = guild_spec

        guild_id = guild_spec.id
        # Local guild_id in bootstrap because it set by Guild.run_agent after object is created
        state_manager_config = GuildHelper.get_state_mgr_config(guild_spec)
        self.state_manager: StateManager = get_state_manager(
            GuildHelper.get_state_manager(guild_spec), state_manager_config
        )

        logging.info(f"Guild Manager is initializing guild {guild_id} - \n{self.original_guild_spec.model_dump()}")

        with Session(self.engine) as session:
            # Get the guild model from the database if it exists.
            guild_model = GuildModel.get_by_id(session, guild_id)

            if guild_model:
                logging.info(f"Guild already exists : [{guild_model}]")
                # Set status to starting to indicate we'll be loading it now
                guild_model.status = GuildStatus.STARTING
                session.add(guild_model)
                session.commit()
            else:
                logging.info(f"Creating new guild : [{guild_spec}]")
                # Create the guild model if it does not exist.
                guild_model = GuildModel.from_guild_spec(guild_spec, self.organization_id)
                guild_model.status = GuildStatus.PENDING_LAUNCH
                session.add(guild_model)

                # Add the agents to the Metastore
                for guild_agent in guild_spec.agents:
                    agent_model = AgentModel.from_agent_spec(guild_id, guild_agent)
                    session.add(agent_model)

            session.commit()
            session.refresh(guild_model)
            self.guild_spec = guild_model.to_guild_spec()

            logging.info(
                f"Guild Manager has stored guild {guild_id} in the metastore - \n{self.guild_spec.model_dump()}"
            )

            # We don't need stale guild health as we will refresh this once manager is ready
            self.agent_health: JsonDict = {}
            self.launch_triggered = False

            for agent_spec in self.guild_spec.agents:
                if agent_spec.id == self.id:
                    continue

                # Set all agents to pending launch, even if they are already running.
                # It will stabilize once the agents send their first heartbeat or respond to the health check.
                self.agent_health[agent_spec.id] = Heartbeat(
                    checktime=datetime.now(),
                    checkstatus=HeartbeatStatus.PENDING_LAUNCH,
                    checkmeta={},
                ).model_dump()

            logging.info(f"Updating state with agent health: \n{self.agent_health}")
            self.state_manager.update_state(
                StateUpdateRequest(
                    state_owner=StateOwner.GUILD,
                    guild_id=self.guild_id,
                    agent_id=self.id,
                    update_path="agents.health",
                    state_update=self.agent_health,
                )
            )

        self.guild: Optional[Guild] = None

    def _add_agent(self, agent_spec: AgentSpec, session: Optional[Session] = None) -> None:
        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        self.guild.launch_agent(agent_spec)

        agent_model = AgentModel.from_agent_spec(self.guild_id, agent_spec)
        if session is None:
            with Session(self.engine) as session:
                if AgentModel.get_by_id(session, self.guild_id, agent_spec.id) is None:
                    session.add(agent_model)
                    session.commit()
                    session.close()
        else:
            if AgentModel.get_by_id(session, self.guild_id, agent_spec.id) is None:
                session.add(agent_model)  # pragma: no cover

    def _announce_guild_refresh(self, ctx: ProcessContext) -> None:
        """
        Announces a guild refresh to all agents.
        """
        with Session(self.engine) as session:
            guild_model = GuildModel.get_by_id(session, self.guild_id)

            if not guild_model:  # pragma: no cover
                logging.error(f"Guild not found: {self.guild_id}")
                ctx.send_error(
                    ErrorMessage(
                        agent_type=self.get_qualified_class_name(),
                        error_type="GUILD_UPDATE_ANNOUNCEMENT_FAILED",
                        error_message=f"Guild not found in Database: {self.guild_id}",
                    )
                )
                return

            guild_spec = guild_model.to_guild_spec()
            self.guild_spec = guild_spec

        guild_updated_announcement = GuildUpdatedAnnouncement(guild_id=self.guild_id, guild_spec=guild_spec)
        ctx._direct_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(GuildUpdatedAnnouncement),
            payload=guild_updated_announcement.model_dump(),
            topics=[GuildTopics.GUILD_STATUS_TOPIC],
        )

        guild_state = self.state_manager.get_state(
            StateFetchRequest(state_owner=StateOwner.GUILD, guild_id=self.guild_id)
        )

        ctx._direct_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(StateFetchResponse),
            payload=guild_state.model_dump(),
            topics=[GuildTopics.GUILD_STATUS_TOPIC],
        )

    def _launch_guild_agents(self, ctx: ProcessContext[SelfReadyNotification]) -> None:
        if self.launch_triggered:
            return  # Indicates that the guild is already launching or launched

        self.launch_triggered = True

        guild_spec = self.original_guild_spec
        logging.info(f"Launching guild agents from {self.id} - \n{guild_spec.model_dump()}")

        for agent_spec in guild_spec.agents:
            if agent_spec.id == self.id:
                continue

            # Set all agents to starting, even if they are already running.
            # It will stabilize once the agents send their first heartbeat or respond to the health check.
            self.agent_health[agent_spec.id] = Heartbeat(
                checktime=datetime.now(),
                checkstatus=HeartbeatStatus.STARTING,
                checkmeta={},
            ).model_dump()

        logging.info(f"Updating state with agent health: \n{self.agent_health}")
        self.state_manager.update_state(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                agent_id=self.id,
                update_path="agents.health",
                state_update=self.agent_health,
            )
        )

        with Session(self.engine) as session:
            # Get the guild model from the database if it exists.
            guild_model = GuildModel.get_by_id(session, self.guild_id)

            if not guild_model:
                # In rare case, if the model is not already created, we need to create it.\
                logging.warning(f"Guild model not found for {self.guild_id}, creating new one")
                guild_model = GuildModel.from_guild_spec(self.guild_spec, self.organization_id)
                guild_model.status = GuildStatus.PENDING_LAUNCH
                session.add(guild_model)

                # Add the agents to the Metastore
                for guild_agent in self.guild_spec.agents:
                    if AgentModel.get_by_id(session, self.guild_id, guild_agent.id) is None:
                        agent_model = AgentModel.from_agent_spec(self.guild_id, guild_agent)
                        session.add(agent_model)

                session.commit()
                session.refresh(guild_model)

            guild_spec = guild_model.to_guild_spec()

            if guild_model.status == GuildStatus.PENDING_LAUNCH:
                # If the guild is not launched, we need to launch it.
                logging.info(f"Guild Manager is Launching guild {self.guild_id}")
                self.guild = GuildBuilder.from_spec(guild_spec).launch(self.organization_id)
            else:
                # If the guild is already launched, we need to load it.
                logging.info(f"Guild Manager is Loading guild {self.guild_id}")
                self.guild = GuildBuilder.from_spec(guild_spec).load_or_launch(self.organization_id)

            self.guild.register_agent(self.get_spec())
            if AgentModel.get_by_id(session, self.guild_id, self.id) is None:
                self_model = AgentModel.from_agent_spec(self.guild_id, self.get_spec())
                session.add(self_model)  # pragma: no cover

            guild_model.status = GuildStatus.STARTING
            session.add(guild_model)
            session.commit()

        healths: List[Heartbeat] = []

        for agent_id, heartbeat in self.agent_health.items():
            logging.info(f"Agent heartbeat {agent_id}: \n{heartbeat}")
            healths.append(Heartbeat.model_validate(heartbeat))

        if self.agent_health:
            ctx._direct_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(AgentsHealthReport),
                payload=AgentsHealthReport.model_validate(
                    {"agents": {k: Heartbeat.model_validate(v) for k, v in self.agent_health.items()}}
                ).model_dump(),
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
            )

        # Let us also send a HealthCheckRequest so already running agents will send a heartbeat
        ctx._direct_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(HealthCheckRequest),
            payload=HealthCheckRequest().model_dump(),
            topics=[HealthConstants.HEARTBEAT_TOPIC],
        )

    @processor(
        SelfReadyNotification,
        predicate=lambda self, msg: msg.sender == self.get_agent_tag() and msg.topic_published_to == self._self_inbox,
        handle_essential=True,
    )
    def launch_guild_agents(self, ctx: ProcessContext[SelfReadyNotification]) -> None:
        """
        Launches the guild agents.
        """
        self._launch_guild_agents(ctx)

    @processor(AgentLaunchRequest)
    def launch_agent(self, ctx: ProcessContext[AgentLaunchRequest]) -> None:
        """
        Adds a member to the guild.
        """
        aar = ctx.payload
        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        self.guild.launch_agent(aar.agent_spec)

        with Session(self.engine) as session:
            if AgentModel.get_by_id(session, self.guild_id, aar.agent_spec.id) is None:
                session.add(AgentModel.from_agent_spec(self.guild_id, aar.agent_spec))
                session.commit()

        self.state_manager.update_state(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                agent_id=self.id,
                update_path=f'agents.health["{aar.agent_spec.id}"]',
                state_update=Heartbeat(
                    checktime=datetime.now(),
                    checkstatus=HeartbeatStatus.STARTING,
                    checkmeta={},
                ).model_dump(),
            )
        )

        agent_addition_response = AgentLaunchResponse(
            agent_id=aar.agent_spec.id,
            status_code=201,
            status="Agent launched successfully",
        )
        ctx.send(agent_addition_response)

        # Announce Guild refresh to all agents
        self._announce_guild_refresh(ctx)

    @processor(AgentListRequest)
    def list_agents(self, ctx: ProcessContext[AgentListRequest]) -> None:
        """
        Lists the agents in the guild.
        """
        alr = ctx.payload
        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        if alr.guild_id == self.guild_id:
            agent_list = self.guild.list_agents()

            agents: List[AgentInfoResponse] = []

            for guild_agent in agent_list:
                agents.append(
                    AgentInfoResponse(
                        id=guild_agent.id,
                        name=guild_agent.name,
                        description=guild_agent.description,
                        class_name=guild_agent.class_name,
                    )
                )

            agent_list_response = AgentListResponse(agents=agents)

            ctx.send(agent_list_response)
        else:  # pragma: no cover
            logging.error(f"Invalid guild id: {alr.guild_id}")
            ctx.send(
                BadInputResponse(
                    error_field="guild_id",
                    message=f"Invalid guild id: {alr.guild_id}",
                )
            )

    @processor(Heartbeat, handle_essential=True)
    def update_agent_status(self, ctx: ProcessContext[Heartbeat]) -> None:
        """
        Updates the agent status in the guild.
        """
        heartbeat: Heartbeat = ctx.payload

        logging.info(f"Received heartbeat: {heartbeat.model_dump()}")

        self.state_manager.update_state(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                agent_id=self.id,
                update_path=f'agents.health["{ctx.message.sender.id}"]',
                state_update=heartbeat.model_dump(),
            )
        )

        agent_health_response = self.state_manager.get_state(
            StateFetchRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                agent_id=self.id,
                state_path="agents.health",
            )
        )

        if agent_health_response.state:
            health_report = AgentsHealthReport.model_validate(
                {"agents": {k: Heartbeat.model_validate(v) for k, v in agent_health_response.state.items()}}
            )

            with Session(self.engine) as session:
                guild_model = GuildModel.get_by_id(guild_id=self.guild_id, session=session)
                guild_status = GuildStatus.UNKNOWN

                if heartbeat.checkstatus == HeartbeatStatus.OK:
                    guild_status = GuildStatus.RUNNING
                elif heartbeat.checkstatus == HeartbeatStatus.WARNING:
                    guild_status = GuildStatus.WARNING
                elif heartbeat.checkstatus == HeartbeatStatus.STARTING:
                    guild_status = GuildStatus.STARTING
                elif heartbeat.checkstatus == HeartbeatStatus.BACKLOGGED:
                    guild_status = GuildStatus.BACKLOGGED
                elif heartbeat.checkstatus == HeartbeatStatus.UNKNOWN:
                    guild_status = GuildStatus.UNKNOWN
                elif heartbeat.checkstatus == HeartbeatStatus.ERROR:
                    guild_status = GuildStatus.ERROR

                if guild_model:
                    guild_model.status = guild_status
                    session.add(guild_model)
                    session.commit()

            ctx._direct_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(AgentsHealthReport),
                payload=health_report.model_dump(),
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
            )

    @processor(RunningAgentListRequest)
    def list_running_agents(self, ctx: ProcessContext[RunningAgentListRequest]) -> None:
        alr = ctx.payload
        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        if alr.guild_id == self.guild_id:
            agent_list = self.guild.list_all_running_agents()

            agents: List[AgentInfoResponse] = []

            for guild_agent in agent_list:
                agents.append(
                    AgentInfoResponse(
                        id=guild_agent.id,
                        name=guild_agent.name,
                        description=guild_agent.description,
                        class_name=guild_agent.class_name,
                    )
                )

            agent_list_response = AgentListResponse(agents=agents)

            ctx.send(agent_list_response)
        else:  # pragma: no cover
            logging.error(f"Invalid guild id: {alr.guild_id}")
            ctx.send(
                BadInputResponse(
                    error_field="guild_id",
                    message=f"Invalid guild id: {alr.guild_id}",
                )
            )

    @processor(AgentGetRequest)
    def get_agent(self, ctx: ProcessContext[AgentGetRequest]) -> None:
        """
        Gets an agent in the guild.
        """
        agr = ctx.payload
        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        if agr.guild_id == self.guild_id:
            guild_agent = self.guild.get_agent(agr.agent_id)

            if guild_agent:
                agent_response = AgentInfoResponse(
                    id=guild_agent.id,
                    name=guild_agent.name,
                    description=guild_agent.description,
                    class_name=guild_agent.class_name,
                )

                ctx.send(agent_response)
            else:  # pragma: no cover
                logging.error(f"Invalid agent id: {agr.agent_id}")
                ctx.send(
                    BadInputResponse(
                        error_field="agent_id",
                        message=f"Invalid agent id: {agr.agent_id}",
                    )
                )
        else:
            logging.error(f"Invalid guild id: {agr.guild_id}")
            ctx.send(
                BadInputResponse(
                    error_field="guild_id",
                    message=f"Invalid guild id: {agr.guild_id}",
                )
            )

    @processor(UserAgentCreationRequest)
    def create_user_agent(self, ctx: agent.ProcessContext[UserAgentCreationRequest]) -> None:
        """
        Creates a user agent.
        """
        uacr = ctx.payload

        # Create a user agent if it is already not present. Else publish a conflict response.

        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        if self.guild.get_agent(UserProxyAgent.get_user_agent_id(uacr.user_id)):
            logging.error(f"Agent for user {uacr.user_id} already exists")
            ctx.send(
                ConflictResponse(
                    error_field="user_id",
                    message=f"Agent for user {uacr.user_id} already exists",
                )
            )

        else:
            user_id = uacr.user_id

            user_agent_spec = (
                AgentBuilder(UserProxyAgent)
                .set_id(UserProxyAgent.get_user_agent_id(user_id))
                .set_name(uacr.user_name)
                .set_description(f"Agent for user {user_id}")
                .set_properties(UserProxyAgentProps(user_id=user_id))
                .add_additional_topic(UserProxyAgent.get_user_inbox_topic(user_id))
                .add_additional_topic(UserProxyAgent.get_user_outbox_topic(user_id))
                .add_additional_topic(UserProxyAgent.get_user_system_notifications_topic(user_id))
                .add_additional_topic(UserProxyAgent.get_user_system_requests_topic(user_id))
                .add_additional_topic(GuildTopics.GUILD_STATUS_TOPIC)
                .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
                .build_spec()
            )

            user_topic = UserProxyAgent.get_user_inbox_topic(user_id)

            self._add_agent(user_agent_spec)

            agent_addition_response = UserAgentCreationResponse(
                user_id=user_id,
                agent_id=user_agent_spec.id,
                status_code=201,
                status="Agent created successfully",
                topic=user_topic,
            )

            self.state_manager.update_state(
                StateUpdateRequest(
                    state_owner=StateOwner.GUILD,
                    guild_id=self.guild_id,
                    agent_id=self.id,
                    update_path="agents.health",
                    state_update={
                        user_agent_spec.id: Heartbeat(
                            checktime=datetime.now(),
                            checkstatus=HeartbeatStatus.STARTING,
                            checkmeta={},
                        ).model_dump()
                    },
                )
            )

            ctx.send(agent_addition_response)

            # Announce Guild refresh to all agents
            self._announce_guild_refresh(ctx)

    @processor(UserAgentGetRequest)
    def get_user_agent(self, ctx: ProcessContext[UserAgentGetRequest]) -> None:
        """
        Gets a user agent.
        """

        uagr = ctx.payload
        user_id = uagr.user_id

        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        user_agent = self.guild.get_agent(UserProxyAgent.get_user_agent_id(user_id))

        if user_agent:
            agent_response = AgentInfoResponse(
                id=user_agent.id,
                name=user_agent.name,
                description=user_agent.description,
                class_name=user_agent.class_name,
            )

            ctx.send(agent_response)
        else:
            logging.error(f"Invalid user id: {user_id}")
            ctx.send(
                BadInputResponse(
                    error_field="user_id",
                    message=f"Invalid user id: {user_id}",
                )
            )

    @processor(StateFetchRequest, handle_essential=True)
    def get_state_handler(self, ctx: ProcessContext[StateFetchRequest]) -> None:
        """
        Gets the state of an agent or the guild.
        """
        sfr = ctx.payload

        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        try:
            state = self.state_manager.get_state(sfr)
            ctx._direct_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(StateFetchResponse),
                payload=state.model_dump(),
                topics=[GuildTopics.STATE_TOPIC],
            )
        except Exception as e:
            ctx.send_error(StateFetchError(state_fetch_request=sfr, error=str(e)))

    @processor(StateUpdateRequest, handle_essential=True)
    def update_state_handler(self, ctx: ProcessContext[StateUpdateRequest]) -> None:
        """
        Updates the state of an agent or the guild.
        """
        if getattr(self, "_shutting_down", False) and getattr(self, "_is_shutdown", False):
            logging.info(f"Guild Manager {self.id} is shutting down")
            return

        sur = ctx.payload

        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        try:
            state_update = self.state_manager.update_state(sur)
            ctx._direct_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(StateUpdateResponse),
                payload=state_update.model_dump(),
                topics=[GuildTopics.STATE_TOPIC],
            )
        except Exception as e:
            ctx.send_error(StateUpdateError(state_update_request=sur, error=str(e)))

    @processor(StopGuildRequest, handle_essential=True)
    def stop_guild(self, ctx: ProcessContext[StopGuildRequest]) -> None:
        """
        Stops all the agents in the guild.
        """
        logging.info(f"Stopping guild {self.guild_id}")
        ctx._direct_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(StopGuildResponse),
            payload=StopGuildResponse(user_id=ctx.payload.user_id).model_dump(),
            topics=[GuildTopics.GUILD_STATUS_TOPIC],
        )

        self._shutting_down = True

        if self.guild is None:
            raise RuntimeError("Guild is not initialized")

        if ctx.payload.guild_id == self.guild_id:
            with Session(self.engine) as session:
                guild_model = GuildModel.get_by_id(session, self.guild_id)
                if guild_model:
                    guild_model.status = GuildStatus.STOPPING
                    session.add(guild_model)
                    session.commit()

            for agent_spec in self.guild.list_agents():
                if agent_spec.id != self.id:
                    self.guild.remove_agent(agent_spec.id)

            with Session(self.engine) as session:
                guild_model = GuildModel.get_by_id(session, self.guild_id)
                if guild_model:
                    guild_model.status = GuildStatus.STOPPED
                    session.add(guild_model)
                    session.commit()

            with Session(self.engine) as session:
                guild_model = GuildModel.get_by_id(session, self.guild_id)
                if guild_model:
                    print(guild_model.model_dump())

            self.guild.remove_agent(self.id)

            logging.info(f"Guild {self.guild_id} stopped")

        self._is_shutdown = True

    @processor(HealthCheckRequest, handle_essential=True)
    def send_heartbeat(self, ctx: ProcessContext[HealthCheckRequest]):

        if getattr(self, "_shutting_down", False) and getattr(self, "_is_shutdown", False):
            logging.info(f"Guild Manager {self.id} is shutting down")
            return

        checkmeta: dict = {}
        if isinstance(self, Agent):
            logging.info(f"Healthcheck from Guild Manager -- {self.get_agent_tag()}")
            status = HeartbeatStatus.OK
            checkmeta = {}
            qos_latency = self.agent_spec.qos.latency
            time_now = datetime.now()
            checktime = ctx.payload.checktime
            msg_latency = (time_now - checktime).total_seconds() * 1000  # Convert to milliseconds
            if qos_latency and msg_latency > qos_latency:
                status = HeartbeatStatus.BACKLOGGED

            checkmeta["qos_latency"] = qos_latency
            checkmeta["observed_latency"] = msg_latency

        hr = Heartbeat(checktime=checktime, checkstatus=status, checkmeta=checkmeta)
        ctx.send(hr)

        # Trigger a guild launch, in case we missed the self ready notification
        if not self.launch_triggered:
            self._launch_guild_agents(ctx)
