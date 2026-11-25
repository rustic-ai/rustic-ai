"""Dependency resolver for uniko memory instances."""

import logging
import threading
from typing import Any, Dict, Literal, Optional, Union, cast

from fsspec.core import url_to_fs
from fsspec.implementations.local import LocalFileSystem
import uniko
from uniko.models import LlmSpecAdapter

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.filesystem.utils import get_uri

from .deployment import validate_deployment
from .runtime import MemoryHandle, MemoryRuntime


def runtime_info(handle):
    if isinstance(handle, MemoryHandle):
        return {
            "streaming": handle._runtime.streaming,
            "instance": handle._runtime.instance,
            "runtime": handle._runtime,
        }
    return None


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
        readiness_policy: Literal["sdk_default", "require_verified"] = "sdk_default",
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
        self._resolution_lock = threading.RLock()
        if readiness_policy != "sdk_default":
            raise ValueError(
                "This integration cannot verify model readiness at startup; require_verified is unavailable"
            )
        self.readiness_policy = readiness_policy
        self.storage_path = storage_path
        self.llm_spec = llm_spec
        self.streaming = streaming
        self.scope_to_agent = scope_to_agent
        self.config = config
        self.embedding = embedding
        self.nlp = nlp
        self.reranker = reranker
        self._closing = False
        self._runtimes: Dict[str, MemoryRuntime] = {}
        self._uniko_instances: Dict[str, uniko.Uniko] = {}

    def get_or_resolve(
        self, org_id: str, guild_id: Optional[str] = None, agent_id: Optional[str] = None
    ) -> uniko.Agent:
        with self._resolution_lock:
            if self._closing:
                raise RuntimeError("Uniko resolver has been shut down")
            return super().get_or_resolve(org_id, guild_id, agent_id)

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> uniko.Agent:
        with self._resolution_lock:
            return self._resolve(org_id, guild_id, agent_id)

    def _resolve(self, org_id: str, guild_id: str, agent_id: str) -> uniko.Agent:
        """Resolve a Uniko handle backed by this agent's private store.

        Args:
            org_id: Organization ID
            guild_id: Guild ID (used as the default Uniko agent ID)
            agent_id: Rustic AI agent ID, determining private filesystem scope.

        Returns:
            uniko.Agent handle in the agent's private store
        """
        if self._closing:
            raise RuntimeError("Uniko resolver has been shut down")
        validate_deployment(self.config or {}, self.reranker)
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
            native_path = None
            if self.storage_path:
                agent_fs = self.inject(FileSystem, "filesystem", org_id, guild_id, agent_id)
                backing_fs, path = url_to_fs(get_uri(agent_fs, "/" + self.storage_path.lstrip("/")))
                if not isinstance(backing_fs, LocalFileSystem):
                    raise ValueError("Uniko persistent storage requires a local agent filesystem")
                native_path = path
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
            self._runtimes[cache_key] = MemoryRuntime(uni, self.streaming, native_path, org_id)

        # Get the uniko instance and return agent handle
        uni = self._uniko_instances[cache_key]

        # Use guild_id as the uniko agent ID (unless scoped to individual agents)
        memory_agent_id = agent_id if self.scope_to_agent else guild_id
        return cast(uniko.Agent, MemoryHandle(uni.agent(memory_agent_id), self._runtimes[cache_key]))

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
        with self._resolution_lock:
            self._shutdown()

    def _shutdown(self):
        """Stop new work, drain accepted calls and drop cached native handles.

        External native handle errors remain visible. Call shutdown_async when
        shutting down from an event loop with work still running.
        """
        self._closing = True
        self.cache.clear()
        for runtime in self._runtimes.values():
            runtime.close()
        self._runtimes.clear()
        self._uniko_instances.clear()

    async def shutdown_async(self):
        with self._resolution_lock:
            await self._shutdown_async()

    async def _shutdown_async(self):
        self._closing = True
        self.cache.clear()
        for runtime in self._runtimes.values():
            await runtime.close_async()
        self._runtimes.clear()
        self._uniko_instances.clear()

    def __del__(self):
        if not hasattr(self, "_runtimes"):
            return
        try:
            self.shutdown()
        except Exception:
            logging.getLogger(__name__).exception("Uniko resolver cleanup failed")
