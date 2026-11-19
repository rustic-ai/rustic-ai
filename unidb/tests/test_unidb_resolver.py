"""Opening and readiness failures never substitute an empty database."""

import pytest
import uni_db

from rustic_ai.unidb.resolver import UniDBResolver
from rustic_ai.unidb.runtime import UniDBRuntime


@pytest.mark.parametrize("scope", ["GUILD_GLOBAL", "ORG_GLOBAL"])
def test_resolver_requires_agent_scope(scope):
    with pytest.raises(ValueError, match="agent-scoped"):
        UniDBResolver(binding_id="test", open_mode="temporary").resolve("org", "guild", scope)


@pytest.mark.parametrize("relative", ["../escape", "/absolute", ""])
def test_resolver_refuses_invalid_path_before_dependency_injection(relative):
    resolver = UniDBResolver(binding_id="test", location={"kind": "filesystem", "relative_path": relative})
    with pytest.raises(ValueError, match="relative path"):
        resolver.resolve("org", "guild", "agent")


def test_existing_schema_mismatch_fails_readiness_and_releases_handle(tmp_path):
    path = str(tmp_path / "store")
    db = uni_db.Uni.create(path)
    db.schema().label("Thing").property("name", "string").apply()
    db.shutdown()
    bootstrap = {
        "policy": "verify_existing",
        "schema": {"labels": [{"name": "Thing", "properties": [{"name": "name", "type": "int64"}]}]},
    }
    with pytest.raises(ValueError, match="differs"):
        UniDBRuntime(uni_db.Uni.open_existing(path), "test", bootstrap, {})
    reopened = uni_db.Uni.open_existing(path)
    try:
        assert reopened.get_label_info("Thing").properties[0].data_type == "string"
    finally:
        reopened.shutdown()
