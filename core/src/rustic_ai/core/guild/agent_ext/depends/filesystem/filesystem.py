from fsspec import filesystem
from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver


class FileSystemResolver(DependencyResolver[FileSystem]):
    def __init__(self, path_base: str, protocol: str, storage_options: dict) -> None:
        super().__init__()
        self.path_base = path_base
        self.protocol = protocol
        self.storage_options = storage_options

    def resolve(self, guild_id: str, agent_id: str) -> FileSystem:
        basefs = filesystem(self.protocol, **self.storage_options)
        return FileSystem(path=f"{self.path_base}/{guild_id}/{agent_id}", fs=basefs)
