"""Dependency resolver for uniko memory instances."""

from typing import Any, Dict, Optional

from fsspec.core import url_to_fs
from fsspec.implementations.local import LocalFileSystem
import uniko

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.filesystem.utils import get_uri


class UnikoResolver(DependencyResolver[uniko.Agent]):
    """Agent-scoped resolver for private Uniko storage.

    Persistent storage is resolved through the injected agent filesystem.
    It never depends on the process working directory.

    Attributes:
        storage_path: Location within the agent filesystem. None selects in-memory storage.
        llm_spec: LLM configuration for answer generation. Format:
                 {"alias": "openai", "model_id": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"}
        streaming: Enable streaming mode for async observations
        scope_to_agent: Scope visibility to agent-level (default: False for guild-wide sharing)
    """

    memoize_resolution: bool = True

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_spec: Optional[Dict[str, Any]] = None,
        streaming: bool = False,
        scope_to_agent: bool = False,
    ):
        """Initialize the UnikoResolver.

        Args:
            storage_path: Location within the agent filesystem. None = in-memory storage.
            llm_spec: Optional LLM configuration dict for answer generation.
            streaming: Enable streaming mode for background processing.
            scope_to_agent: If True, scope memory to individual agents (not recommended).
        """
        super().__init__()
        self.storage_path = storage_path
        self.llm_spec = llm_spec
        self.streaming = streaming
        self.scope_to_agent = scope_to_agent
        self._uniko_instances: Dict[str, uniko.Uniko] = {}

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> uniko.Agent:
        """Resolve a Uniko handle backed by this agent's private store.

        Args:
            org_id: Organization ID
            guild_id: Guild ID (becomes the uniko agent ID for shared memory)
            agent_id: Rustic AI agent ID, determining private filesystem scope.

        Returns:
            uniko.Agent handle in the agent's private store
        """
        cache_key = f"{org_id}:{guild_id}:{agent_id}"

        # Lazy initialization of uniko instance
        if cache_key not in self._uniko_instances:
            builder = uniko.Uniko.builder()

            # Configure storage
            if self.storage_path:
                agent_fs = self.inject(FileSystem, "filesystem", org_id, guild_id, agent_id)
                backing_fs, path = url_to_fs(get_uri(agent_fs, "/" + self.storage_path.lstrip("/")))
                if not isinstance(backing_fs, LocalFileSystem):
                    raise ValueError("Uniko persistent storage requires a local agent filesystem")
                builder = builder.path(path)
            else:
                builder = builder.in_memory()

            # Configure LLM if provided
            if self.llm_spec:
                llm = self._build_llm_spec(self.llm_spec)
                builder = builder.llm(llm)

            # Configure streaming mode
            if self.streaming:
                builder = builder.streaming(True)

            # Configure visibility scope
            if self.scope_to_agent:
                builder = builder.scope_to_agent()

            # Build synchronously (async version needs different pattern)
            uni = builder.build_sync()
            self._uniko_instances[cache_key] = uni

        # Get the uniko instance and return agent handle
        uni = self._uniko_instances[cache_key]

        # Use guild_id as the uniko agent ID (unless scoped to individual agents)
        memory_agent_id = agent_id if self.scope_to_agent else guild_id
        return uni.agent(memory_agent_id)

    def _build_llm_spec(self, spec: Dict[str, Any]) -> Any:
        """Build uniko LLM spec from configuration dict.

        Args:
            spec: Dict with keys: alias, model_id, key_env, base_url (optional)

        Returns:
            uniko LLM spec object
        """
        provider_alias = spec.get("alias", "openai")
        model_id = spec.get("model_id", "gpt-4o-mini")

        # Build LLM spec based on provider alias
        if provider_alias == "openai":
            key_env = spec.get("key_env", "OPENAI_API_KEY")
            base_url = spec.get("base_url")

            # Uniko requires alias in 'task/provider' format
            alias = f"answer/{provider_alias}"
            llm = uniko.LlmSpec.openai_with_key_env(alias, model_id, key_env, base_url=base_url)
            return llm

        elif provider_alias == "mistral":
            # Uniko 0.5 uses OpenAI-compatible endpoints for hosted models.
            alias = f"answer/{provider_alias}"
            llm = uniko.LlmSpec.openai_with_key_env(
                alias,
                model_id,
                spec.get("key_env", "MISTRAL_API_KEY"),
                base_url=spec.get("base_url", "https://api.mistral.ai/v1"),
            )
            return llm

        else:
            raise ValueError(f"Unsupported LLM alias: {provider_alias}")

    def shutdown(self):
        """Shutdown all uniko instances managed by this resolver.

        Note: Uniko requires all Agent and Session handles to be dropped before shutdown.
        In test scenarios, this may result in warnings that can be safely ignored.
        """
        for cache_key, uni in self._uniko_instances.items():
            try:
                uni.shutdown_sync()
            except Exception as e:
                error_msg = str(e)
                # Suppress expected cleanup warnings about handles not being dropped
                if "Agent and Session handles" not in error_msg:
                    # Log unexpected errors
                    print(f"Error shutting down uniko instance {cache_key}: {e}")

        self._uniko_instances.clear()

    def __del__(self):
        """Cleanup on garbage collection."""
        self.shutdown()
