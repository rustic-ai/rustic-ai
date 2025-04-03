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
    AgentMode,
    AgentSpec,
    AgentType,
    GuildTopics,
    agent,
)
from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, GuildHelper
from rustic_ai.core.guild.metastore import AgentModel, GuildModel, Metastore
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateError,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.class_utils import get_state_manager
from rustic_ai.core.utils.priority import Priority


class GuildManagerAgent(Agent[GuildManagerAgentProps]):
    def __init__(
        self,
        agent_spec: AgentSpec[GuildManagerAgentProps],
    ):
        guild_spec = agent_spec.props.guild_spec
        database_url = agent_spec.props.database_url

        self.database_url = database_url
        self.engine = Metastore.get_engine(database_url)

        self.guild_spec_json = guild_spec.model_dump_json()

        guild_id = (
            guild_spec.id
        )  # Local guild_id in bootstrap because it set by Guild.run_agent after object is created

        self.guild_name = guild_spec.name
        self.manager_agent_name = f"{guild_spec.name}_manager"

        agent_spec.id = f"{guild_spec.id}#manager_agent"
        agent_spec.name = self.manager_agent_name
        agent_spec.description = f"An agent with ability to manage the guild: {self.guild_name}"
        agent_spec.additional_topics.append(GuildTopics.SYSTEM_TOPIC)

        super().__init__(
            agent_spec,
            AgentType.BOT,
            AgentMode.LOCAL,
        )

        self.state_manager = get_state_manager(GuildHelper.get_state_manager(guild_spec))

        with Session(self.engine) as session:
            # Get the guild model from the database if it exists.
            self.guild_model = GuildModel.get_by_id(session, guild_id)

            if self.guild_model:
                logging.info(f"Loading existing guild : [{self.guild_model}]")
                self.guild_spec = self.guild_model.to_guild_spec()
                self.guild = GuildBuilder.from_spec(self.guild_spec).load()
            else:
                logging.info(f"Creating new guild : [{guild_spec}]")
                # Create the guild model if it does not exist.
                self.guild = GuildBuilder.from_spec(guild_spec).launch()
                self.guild_spec = self.guild.to_spec()
                self.guild_model = GuildModel.from_guild_spec(guild_spec)
                session.add(self.guild_model)

                # Add the agents to the Metastore
                for guild_agent in self.guild.list_agents():
                    agent_model = AgentModel.from_agent_spec(guild_id, guild_agent)
                    session.add(agent_model)

                session.commit()

            # Register self with the guild and add to the metastore
            self_spec = agent_spec
            self.guild.register_agent(self_spec)
            self_model = AgentModel.from_agent_spec(guild_id, self_spec)
            session.add(self_model)
            session.commit()

            session.close()

            # TODO: Announce Guild state to all agents

    def _add_agent(self, agent_spec: AgentSpec, session: Optional[Session] = None) -> None:
        self.guild.launch_agent(agent_spec)

        agent_model = AgentModel.from_agent_spec(self.guild_id, agent_spec)

        if session is None:
            with Session(self.engine) as session:
                session.add(agent_model)
                session.commit()
                session.close()
        else:
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
        ctx._raw_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(GuildUpdatedAnnouncement),
            payload=guild_updated_announcement.model_dump(),
            topics=[GuildTopics.GUILD_STATUS_TOPIC],
        )

        guild_state = self.state_manager.get_state(
            StateFetchRequest(state_owner=StateOwner.GUILD, guild_id=self.guild_id)
        )
        ctx._raw_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(StateFetchResponse),
            payload=guild_state.model_dump(),
            topics=[GuildTopics.GUILD_STATUS_TOPIC],
        )

    @processor(AgentLaunchRequest)
    def launch_agent(self, ctx: ProcessContext[AgentLaunchRequest]) -> None:
        """
        Adds a member to the guild.
        """
        aar = ctx.payload
        self.guild.launch_agent(aar.agent_spec)
        with Session(self.engine) as session:
            session.add(AgentModel.from_agent_spec(self.guild_id, aar.agent_spec))
            session.commit()

        agent_addition_response = AgentLaunchResponse(
            agent_id=aar.agent_spec.id,
            status_code=201,
            status="Agent launched successfully",
        )
        ctx.send(agent_addition_response)

        # Announce Guild refesh to all agents
        self._announce_guild_refresh(ctx)

    @processor(AgentListRequest)
    def list_agents(self, ctx: ProcessContext[AgentListRequest]) -> None:
        """
        Lists the agents in the guild.
        """
        alr = ctx.payload
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

    @processor(RunningAgentListRequest)
    def list_running_agents(self, ctx: ProcessContext[RunningAgentListRequest]) -> None:
        alr = ctx.payload
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
        try:
            state = self.state_manager.get_state(sfr)
            ctx._raw_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(StateFetchResponse),
                payload=state.model_dump(),
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
            )
        except Exception as e:
            ctx.send_error(StateUpdateError(state_update_request=sfr, error=str(e)))

    @processor(StateUpdateRequest, handle_essential=True)
    def update_state_handler(self, ctx: ProcessContext[StateUpdateRequest]) -> None:
        """
        Updates the state of an agent or the guild.
        """
        sur = ctx.payload

        try:
            state_update = self.state_manager.update_state(sur)
            ctx._raw_send(
                priority=Priority.NORMAL,
                format=get_qualified_class_name(StateUpdateResponse),
                payload=state_update.model_dump(),
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
            )
        except Exception as e:
            ctx.send_error(StateUpdateError(state_update_request=sur, error=str(e)))
