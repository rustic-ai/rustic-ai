# UniDBResolver

`rustic_ai.unidb.resolver.UniDBResolver` provides an agent-scoped `UniDBRuntime` to [UniDBAgent](../../agents/unidb/index.md). It opens native Uni-DB 5.2.1, applies or verifies bootstrap definitions, and caches the runtime for that agent. Guild- and organization-scoped resolution is rejected.

## Configuration

| Property | Default | Meaning |
| --- | --- | --- |
| `binding_id` | Required | Stable logical identity; must match agent properties |
| `open_mode` | `open_existing` | Existing store, explicit `create`, or disposable `temporary` |
| `location` | `{}` | Persistent mode requires `kind: filesystem`, `dependency_key`, and `relative_path` |
| `native_config` | `{}` | Version-specific native settings, such as WAL and strict schema |
| `bootstrap` | `policy: verify_existing` | `apply_to_new` for create/temporary, or verification of existing definitions |
| `receipts` | `mode: same_transaction`, `namespace: __rustic_unidb` | Connector-owned ordinary-effect bookkeeping |

A temporary binding does not require a filesystem dependency. Persistent paths must be nonempty, relative, and contain no `..` traversal. The filesystem key defaults to `filesystem`. The local adapter translates `file://` into a native path for the pinned binding; remote storage certification is outside this integration's tested support.

## Persistent configuration

Place both dependencies in the database agent's dependency map. This example explicitly creates a new local store; choose `open_existing` and `verify_existing` for reopening it with the same organization/guild/agent identity and path.

```python
from rustic_ai.core.guild.dsl import DependencySpec

persistent_dependencies = {
    "filesystem": DependencySpec(
        class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem.FileSystemResolver",
        properties={"path_base": "/tmp/rustic-db-demo", "protocol": "file", "storage_options": {}},
    ),
    "unidb": DependencySpec(
        class_name="rustic_ai.unidb.resolver.UniDBResolver",
        properties={
            "binding_id": "products-db",
            "open_mode": "create",
            "location": {"kind": "filesystem", "dependency_key": "filesystem", "relative_path": "products"},
            "native_config": {"wal_enabled": True, "strict_schema": True},
            "bootstrap": {
                "policy": "apply_to_new",
                "revision": "products-v1",
                "schema": {
                    "labels": [{"name": "Product", "properties": [{"name": "name", "type": "string"}]}],
                },
            },
            "receipts": {"mode": "same_transaction", "namespace": "__rustic_unidb"},
        },
    ),
}
```

The filesystem resolver scopes the location beneath the configured base using organization, guild, and agent identities. Keep these stable when reopening. `create` refuses an existing store; a failed `open_existing` never falls back to `create` or temporary storage.

## Bootstrap and lifecycle

Bootstrap supports supplied label/edge/property definitions and Locy programs. Verification checks required schema definitions and the connector's recorded bootstrap rule digest. It does not detect out-of-band mutations of the native rule registry. Protect connector metadata through deployment and application policy.

The runtime owns native handles, sessions, transactions, and receipt resources. Messages carry serializable values and identifiers. One authoritative write owner is supported; a shared location and dependency scope do not establish cross-process sharing or safe multiple writers.

The general Rustic resource shutdown hook is deferred. The embedding lifecycle owner must hold the actual resolver instance and call `resolver.close()` before `guild.shutdown()`. The [diagnostics runner](../../agents/unidb/index.md#run-complete-examples) demonstrates this ownership. Repeated close is safe; do not promise managed shutdown merely because a guild has stopped.
