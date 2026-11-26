"""Delayed state responses must not roll back the current agent or guild view."""

from types import SimpleNamespace

import pytest

from rustic_ai.core.guild.agent_ext.mixins.state_refresher import StateRefresherMixin
from rustic_ai.core.state.models import (
    StateFetchResponse,
    StateOwner,
    StateUpdateResponse,
)


class Observer(StateRefresherMixin):
    id, guild_id = "observer", "guild"

    def __init__(self):
        self.observed = []

    def on_state_updated(self, state, ctx):
        self.observed.append(state)


def update(agent, version, state, owner=StateOwner.GUILD, agent_id=None, guild_id="guild"):
    response = StateUpdateResponse(
        state_owner=owner, guild_id=guild_id, agent_id=agent_id, state=state, version=version, timestamp=version
    )
    StateRefresherMixin.update_local_state_on_update.__wfn__(agent, SimpleNamespace(payload=response))


@pytest.mark.parametrize("owner", [StateOwner.GUILD, StateOwner.AGENT])
def test_old_snapshot_does_not_roll_back_state_or_trigger_callback(owner):
    agent = Observer()
    update(agent, 3, {"current": True}, owner, agent.id)
    update(agent, 2, {"stale": True}, owner, agent.id)
    state = agent._guild_state if owner == StateOwner.GUILD else agent._state
    assert state == {"current": True}
    assert agent.observed == [{"current": True}]


def test_versions_are_independent_for_each_owner_and_instance():
    first, second = Observer(), Observer()
    update(first, 5, {"guild": True})
    update(first, 2, {"agent": True}, StateOwner.AGENT, first.id)
    update(second, 1, {"other": True})
    assert first._guild_state == {"guild": True}
    assert first._state == {"agent": True}
    assert second._guild_state == {"other": True}


def test_foreign_guild_and_agent_updates_are_ignored():
    agent = Observer()
    update(agent, 50, {"foreign": True}, guild_id="other")
    update(agent, 50, {"foreign": True}, StateOwner.AGENT, "other")
    assert not agent.observed
    update(agent, 1, {"own": True})
    assert agent._guild_state == {"own": True}


@pytest.mark.parametrize("is_latest,path", [(True, None), (True, ""), (False, None), (True, "nested")])
def test_fetch_results_preserve_current_full_snapshot(is_latest, path):
    agent = Observer()
    update(agent, 3, {"current": True})
    response = StateFetchResponse(
        state_owner=StateOwner.GUILD,
        guild_id="guild",
        state={"fetched": True},
        version=4,
        timestamp=4,
        fetch_timestamp=4,
        is_latest=is_latest,
        state_path=path,
    )
    StateRefresherMixin.update_local_state.__wfn__(agent, SimpleNamespace(payload=response))
    update(agent, 2, {"delayed": True})
    assert agent._guild_state == ({"fetched": True} if is_latest and not path else {"current": True})
    assert agent.observed[-1] == {"fetched": True}
