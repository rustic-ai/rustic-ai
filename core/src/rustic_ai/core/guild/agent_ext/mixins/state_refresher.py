from typing import Optional

from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.messaging import JsonDict
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
    StateUpdateResponse,
)


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
        ctx.send(
            StateFetchRequest(
                state_owner=StateOwner.AGENT,
                guild_id=self.guild_id,
                agent_id=self.id,
                state_path=state_path,
                version=version,
                timestamp=timestamp,
            )
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
        ctx.send(
            StateFetchRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                state_path=state_path,
                version=version,
                timestamp=timestamp,
            )
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
        ctx.send(
            StateUpdateRequest(
                state_owner=StateOwner.AGENT,
                guild_id=self.guild_id,
                agent_id=self.id,
                update_format=update_format,
                state_update=update,
                update_path=update_path,
                update_version=update_version,
                update_timestamp=update_timestamp,
            )
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
        ctx.send(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self.guild_id,
                update_format=update_format,
                state_update=update,
                update_path=update_path,
                update_version=update_version,
                update_timestamp=update_timestamp,
            )
        )

    @processor(StateFetchResponse, handle_essential=True)
    def update_local_state(self, ctx: ProcessContext[StateFetchResponse]):
        sfr = ctx.payload

        if sfr.state_owner == StateOwner.GUILD:
            self._guild_state = sfr.state
        elif sfr.state_owner == StateOwner.AGENT and sfr.agent_id == self.id:
            self._state = sfr.state

    @processor(StateUpdateResponse, handle_essential=True)
    def update_local_state_on_update(self, ctx: ProcessContext[StateUpdateResponse]):
        sur = ctx.payload

        if sur.state_owner == StateOwner.GUILD:
            self._guild_state = sur.state
        elif sur.state_owner == StateOwner.AGENT and sur.agent_id == self.id:
            self._state = sur.state
