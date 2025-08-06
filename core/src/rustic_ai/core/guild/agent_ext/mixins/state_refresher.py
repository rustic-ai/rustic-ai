import logging
from typing import Optional

from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging import JsonDict, Priority
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class StateRefresherMixin:
    id: str
    guild_id: str
    _state: JsonDict = {}
    _guild_state: JsonDict = {}

    def request_state(
        self,
        ctx: ProcessContext,
        state_path: Optional[str] = None,
        version: Optional[int] = None,
        timestamp: Optional[int] = None,
    ):
        """
        Request the state of the agent.
        """
        asfr = StateFetchRequest(
            state_owner=StateOwner.AGENT,
            guild_id=self.guild_id,
            agent_id=self.id,
            state_path=state_path,
            version=version,
            timestamp=timestamp,
        )

        ctx._direct_send(
            priority=Priority.NORMAL,
            topics=[GuildTopics.STATE_TOPIC],
            payload=asfr.model_dump(),
            format=get_qualified_class_name(StateFetchRequest),
        )

    def request_guild_state(
        self,
        ctx: ProcessContext,
        state_path: Optional[str] = None,
        version: Optional[int] = None,
        timestamp: Optional[int] = None,
    ):
        """
        Request the state of the guild.
        """
        gsfr = StateFetchRequest(
            state_owner=StateOwner.GUILD,
            guild_id=self.guild_id,
            state_path=state_path,
            version=version,
            timestamp=timestamp,
        )

        ctx._direct_send(
            priority=Priority.NORMAL,
            topics=[GuildTopics.STATE_TOPIC],
            payload=gsfr.model_dump(),
            format=get_qualified_class_name(StateFetchRequest),
        )

    def update_state(
        self,
        ctx: ProcessContext,
        update_format: StateUpdateFormat,
        update: JsonDict,
        update_path: Optional[str] = None,
        update_version: Optional[int] = None,
        update_timestamp: Optional[int] = None,
    ):
        """
        Update the state of the agent.
        """
        asu = StateUpdateRequest(
            state_owner=StateOwner.AGENT,
            guild_id=self.guild_id,
            agent_id=self.id,
            update_format=update_format,
            state_update=update,
            update_path=update_path,
            update_version=update_version,
            update_timestamp=update_timestamp,
        )

        ctx._direct_send(
            priority=Priority.HIGH,
            topics=[GuildTopics.STATE_TOPIC],
            payload=asu.model_dump(),
            format=get_qualified_class_name(StateUpdateRequest),
        )

    def update_guild_state(
        self,
        ctx: ProcessContext,
        update_format: StateUpdateFormat,
        update: JsonDict,
        update_path: Optional[str] = None,
        update_version: Optional[int] = None,
        update_timestamp: Optional[int] = None,
    ):
        """
        Update the state of the guild.
        """
        gsu = StateUpdateRequest(
            state_owner=StateOwner.GUILD,
            guild_id=self.guild_id,
            update_format=update_format,
            state_update=update,
            update_path=update_path,
            update_version=update_version,
            update_timestamp=update_timestamp,
        )
        ctx._direct_send(
            priority=Priority.HIGH,
            topics=[GuildTopics.STATE_TOPIC],
            payload=gsu.model_dump(),
            format=get_qualified_class_name(StateUpdateRequest),
        )

    def on_state_updated(self, new_state: JsonDict, ctx: ProcessContext[StateUpdateResponse]):
        """
        This method can be overridden to handle state updates.
        """
        pass

    @processor(StateFetchResponse, handle_essential=True)
    def update_local_state(self, ctx: ProcessContext[StateFetchResponse]):
        sfr = ctx.payload

        if sfr.state_owner == StateOwner.GUILD:
            self._guild_state = sfr.state
        elif sfr.state_owner == StateOwner.AGENT and sfr.agent_id == self.id:
            self._state = sfr.state

        self.on_state_updated(sfr.state, ctx)

    @processor(StateUpdateResponse, handle_essential=True)
    def update_local_state_on_update(self, ctx: ProcessContext[StateUpdateResponse]):
        sur = ctx.payload

        logging.debug(f"State update received: {sur.state_owner} {sur.guild_id} {sur.agent_id}")

        if sur.state_owner == StateOwner.GUILD:
            self._guild_state = sur.state
        elif sur.state_owner == StateOwner.AGENT and sur.agent_id == self.id:
            self._state = sur.state

        self.on_state_updated(sur.state, ctx)
