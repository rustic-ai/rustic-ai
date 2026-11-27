from typing import get_args, get_origin

from fsspec.implementations.dirfs import DirFileSystem

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.code_execution.stateless import (
    CodeRunner,
    InProcessCodeInterpreterResolver,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystemResolver
from rustic_ai.core.guild.agent_ext.depends.kvstore import (
    BaseKVStore,
    InMemoryKVStoreResolver,
)


def _provided_type(resolver: type[DependencyResolver]) -> type:
    for base in resolver.__orig_bases__:
        if get_origin(base) is DependencyResolver:
            return get_args(base)[0]
    raise AssertionError(f"{resolver.__name__} does not declare DependencyResolver[T]")


def test_core_resolvers_declare_interface_contracts():
    assert _provided_type(InMemoryKVStoreResolver) is BaseKVStore
    assert _provided_type(FileSystemResolver) is DirFileSystem
    assert _provided_type(InProcessCodeInterpreterResolver) is CodeRunner


def test_kvstore_and_code_runner_resolve_their_interfaces():
    kvstore = InMemoryKVStoreResolver().resolve("org", "guild", "agent")
    runner = InProcessCodeInterpreterResolver().resolve("org", "guild", "agent")

    assert isinstance(kvstore, BaseKVStore)
    assert isinstance(runner, CodeRunner)
