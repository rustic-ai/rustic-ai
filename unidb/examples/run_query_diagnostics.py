"""Run the composed query diagnostics guild from the repository root.

PYTHONPATH=unidb/src:showcase/src python unidb/examples/run_query_diagnostics.py
"""

import json
from pathlib import Path
import time

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.showcase.unidb_query_diagnostics import RunIndexComparison

APP = Path(__file__).resolve().parents[2] / "showcase/apps/unidb_query_diagnostics.json"


def run_comparison(timeout=30):
    spec = GuildSpec.model_validate(json.loads(APP.read_text())["spec"], context={"require_agent_class": True})
    agents = spec.agents
    guild = GuildBuilder.from_spec(spec.model_copy(update={"agents": []})).launch("diagnostics-demo")
    database = None
    try:
        for agent_spec in agents:
            actual = guild._add_local_agent(agent_spec)
            if agent_spec.id == "diagnostics-db":
                database = actual
        caller = guild._add_local_agent(
            AgentBuilder(ProbeAgent)
            .set_id("diagnostics-caller")
            .set_name("Diagnostics caller")
            .set_description("Start and observe the comparison")
            .add_additional_topic("diagnostics.results")
            .listen_to_default_topic(False)
            .build_spec()
        )
        caller.publish_with_guild_route(
            "diagnostics.start", RunIndexComparison(request_id="comparison:1", correlation_id="comparison:1")
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for message in caller.get_messages():
                if message.payload.get("request_id") == "comparison:1":
                    return message.payload
            time.sleep(0.01)
        raise TimeoutError("The diagnostics guild did not produce a terminal result")
    finally:
        # The general Rustic resource shutdown hook remains deferred.
        if database is not None:
            database._dependency_resolvers["unidb"].close()
        guild.shutdown()


if __name__ == "__main__":
    print(json.dumps(run_comparison(), indent=2))
