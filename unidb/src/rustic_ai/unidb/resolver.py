"""Agent-scoped native binding resolver."""

from pathlib import PurePosixPath

from fsspec.core import url_to_fs
from fsspec.implementations.local import LocalFileSystem
import uni_db

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.filesystem.utils import get_uri

from .runtime import UniDBRuntime


class UniDBResolver(DependencyResolver[UniDBRuntime]):
    def __init__(
        self, binding_id, open_mode="open_existing", location=None, native_config=None, bootstrap=None, receipts=None
    ):
        super().__init__()
        if open_mode not in ("open_existing", "create", "temporary"):
            raise ValueError("Unsupported open_mode")
        self.binding_id, self.open_mode = binding_id, open_mode
        self.location, self.native_config = location or {}, native_config or {}
        self.bootstrap = bootstrap or {"policy": "verify_existing"}
        self.receipts = receipts or {"mode": "same_transaction", "namespace": "__rustic_unidb"}
        if self.bootstrap.get("policy") == "apply_to_new" and open_mode not in ("create", "temporary"):
            raise ValueError("apply_to_new requires explicit create")

    def resolve(self, org_id, guild_id, agent_id):
        if not agent_id or agent_id in ("GUILD_GLOBAL", "ORG_GLOBAL"):
            raise ValueError("UniDB runtime must be agent-scoped")
        if self.open_mode == "temporary":
            builder = uni_db.Uni.builder().temporary()
        else:
            if self.location.get("kind") != "filesystem":
                raise ValueError("Persistent bindings require an injected filesystem location")
            relative = self.location.get("relative_path", "")
            if not relative or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
                raise ValueError("Location must be a nonempty relative path without traversal")
            fs = self.inject(FileSystem, self.location.get("dependency_key", "filesystem"), org_id, guild_id, agent_id)
            uri = get_uri(fs, relative)
            backing, native_path = url_to_fs(uri)
            # 5.2.1's local opener expects a path, not a file:// URL.
            location = native_path if isinstance(backing, LocalFileSystem) else uri
            builder = getattr(uni_db.Uni.builder(), self.open_mode)(location)
        db = builder.config(self.native_config).build()
        return UniDBRuntime(db, self.binding_id, self.bootstrap, self.receipts)

    def close(self):
        for runtime in self.cache.values():
            runtime.close()
