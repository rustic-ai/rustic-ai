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
    _agent_state_version: int = -1
    _guild_state_version: int = -1

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

    def _apply_snapshot(self, owner: StateOwner, agent_id: Optional[str], state: JsonDict, version: int) -> bool:
        """Keep a newer full snapshot when responses arrive out of order."""
        if owner == StateOwner.GUILD:
            if version < self._guild_state_version:
                return False
            self._guild_state, self._guild_state_version = state, version
        elif owner == StateOwner.AGENT and agent_id == self.id:
            if version < self._agent_state_version:
                return False
            self._state, self._agent_state_version = state, version
        else:
            return False
        return True

    @processor(StateFetchResponse, handle_essential=True)
    def update_local_state(self, ctx: ProcessContext[StateFetchResponse]):
        sfr = ctx.payload
        if sfr.guild_id != self.guild_id:
            return
        # Historical and path-scoped fetches are intentional query results; they
        # must not replace the current full state used by ordinary processors.
        if sfr.is_latest and not sfr.state_path:
            if not self._apply_snapshot(sfr.state_owner, sfr.agent_id, sfr.state, sfr.version):
                return
        self.on_state_updated(sfr.state, ctx)

    @processor(StateUpdateResponse, handle_essential=True)
    def update_local_state_on_update(self, ctx: ProcessContext[StateUpdateResponse]):
        sur = ctx.payload
        logging.debug(f"State update received: {sur.state_owner} {sur.guild_id} {sur.agent_id}")
        if sur.guild_id != self.guild_id:
            return
        if self._apply_snapshot(sur.state_owner, sur.agent_id, sur.state, sur.version):
            self.on_state_updated(sur.state, ctx)
