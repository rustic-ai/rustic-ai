"""Dependency resolver for uniko memory instances."""

from typing import Any, Dict, Optional, Union

from fsspec.core import url_to_fs
from fsspec.implementations.local import LocalFileSystem
import uniko
from uniko.models import LlmSpecAdapter

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
        llm_spec: Native Uniko LLM configuration with provider, alias and model_id.
        config: Partial native Uniko configuration, merged onto SDK defaults.
        embedding: Native embedding preset or partial configuration.
        nlp: Native NLP preset or partial configuration.
        reranker: Native reranker preset or partial configuration; False disables it.
        streaming: Enable streaming mode for async observations
        scope_to_agent: Restrict visibility to the Uniko agent within its private store
    """

    memoize_resolution: bool = True

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_spec: Optional[Dict[str, Any]] = None,
        streaming: bool = False,
        scope_to_agent: bool = False,
        config: Optional[Dict[str, Any]] = None,
        embedding: Optional[Union[str, Dict[str, Any]]] = None,
        nlp: Optional[Union[str, Dict[str, Any]]] = None,
        reranker: Optional[Union[str, Dict[str, Any], bool]] = None,
    ):
        """Initialize the UnikoResolver.

        Args:
            storage_path: Location within the agent filesystem. None = in-memory storage.
            llm_spec: Optional LLM configuration dict for answer generation.
            streaming: Enable streaming mode for background processing.
            scope_to_agent: If True, restrict visibility to the Uniko agent.
            config: Partial Uniko config, validated by the native SDK.
            embedding: Embedding preset or section, overriding config.embedding.
            nlp: NLP preset or section, overriding config.nlp.
            reranker: Reranker preset or section, overriding config.reranker;
                False disables reranking, None keeps the SDK/config default.
        """
        super().__init__()
        self.storage_path = storage_path
        self.llm_spec = llm_spec
        self.streaming = streaming
        self.scope_to_agent = scope_to_agent
        self.config = config
        self.embedding = embedding
        self.nlp = nlp
        self.reranker = reranker
        self._uniko_instances: Dict[str, uniko.Uniko] = {}

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> uniko.Agent:
        """Resolve a Uniko handle backed by this agent's private store.

        Args:
            org_id: Organization ID
            guild_id: Guild ID (used as the default Uniko agent ID)
            agent_id: Rustic AI agent ID, determining private filesystem scope.

        Returns:
            uniko.Agent handle in the agent's private store
        """
        cache_key = f"{org_id}:{guild_id}:{agent_id}"

        # Lazy initialization of uniko instance
        if cache_key not in self._uniko_instances:
            builder = uniko.Uniko.builder()
            if self.config is not None:
                builder = builder.config(self.config)
            if self.embedding is not None:
                builder = builder.embedding(self.embedding)
            if self.nlp is not None:
                builder = builder.nlp(self.nlp)
            if self.reranker is not None:
                if self.reranker is True:
                    raise ValueError("Use a reranker preset or configuration to enable reranking")
                builder = builder.reranker(None if self.reranker is False else self.reranker)

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
        """Validate native SDK modes, preserving the established OpenAI input."""
        native_spec = dict(spec)
        if "provider" not in native_spec:
            # Existing Rustic configurations used alias as a provider selector.
            legacy_alias = native_spec.get("alias", "openai")
            if legacy_alias in {"mistral", "mistralrs"}:
                raise ValueError("The embedded mistralrs runtime is no longer supported; configure an SDK provider")
            if legacy_alias != "openai":
                raise ValueError(f"Unsupported LLM alias: {legacy_alias}")
            native_spec.update(
                provider="openai_with_key_env",
                alias="answer/openai",
                model_id=native_spec.get("model_id", "gpt-4o-mini"),
                key_env=native_spec.get("key_env", "OPENAI_API_KEY"),
            )
        return LlmSpecAdapter.validate_python(native_spec).to_native()

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
