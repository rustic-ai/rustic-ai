"""Dependency resolver for uniko memory instances."""

from typing import Dict, Optional, Any
import uniko
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencyResolver


class UnikoResolver(DependencyResolver[uniko.Agent]):
    """Guild-scoped resolver for uniko agents.

    Creates one uniko.Uniko instance per guild and returns agent handles
    scoped to the guild_id. This enables memory sharing across all agents
    in a guild while maintaining isolation between different guilds.

    Attributes:
        storage_path: Path template for persistent storage (supports {org_id}/{guild_id} formatting).
                     If None, uses in-memory storage.
        llm_spec: LLM configuration for answer generation. Format:
                 {"alias": "openai", "model_id": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"}
        streaming: Enable streaming mode for async observations
        scope_to_agent: Scope visibility to agent-level (default: False for guild-wide sharing)
    """

    memoize_resolution: bool = True  # Cache per guild

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_spec: Optional[Dict[str, Any]] = None,
        streaming: bool = False,
        scope_to_agent: bool = False,
    ):
        """Initialize the UnikoResolver.

        Args:
            storage_path: Optional path template with {org_id}/{guild_id} placeholders.
                         None = in-memory storage.
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
        """Resolve a uniko.Agent handle scoped to the guild.

        Args:
            org_id: Organization ID
            guild_id: Guild ID (becomes the uniko agent ID for shared memory)
            agent_id: Rustic AI agent ID (not used unless scope_to_agent=True)

        Returns:
            uniko.Agent handle for the guild's shared memory context
        """
        # Cache key: org:guild for guild-scoped instances
        cache_key = f"{org_id}:{guild_id}"

        # Lazy initialization of uniko instance
        if cache_key not in self._uniko_instances:
            builder = uniko.Uniko.builder()

            # Configure storage
            if self.storage_path:
                path = self.storage_path.format(
                    org_id=org_id,
                    guild_id=guild_id
                )
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
        alias = spec.get("alias", "openai")
        model_id = spec.get("model_id", "gpt-4o-mini")

        # Build LLM spec based on alias
        if alias == "openai":
            import os
            api_key = os.getenv(spec.get("key_env", "OPENAI_API_KEY"))
            base_url = spec.get("base_url")

            llm = uniko.LLM.openai(model_id, api_key=api_key)
            if base_url:
                llm = llm.base_url(base_url)
            return llm

        elif alias == "mistral":
            import os
            api_key = os.getenv(spec.get("key_env", "MISTRAL_API_KEY"))
            llm = uniko.LLM.mistral(model_id, api_key=api_key)
            return llm

        else:
            raise ValueError(f"Unsupported LLM alias: {alias}")

    def shutdown(self):
        """Shutdown all uniko instances managed by this resolver."""
        for cache_key, uni in self._uniko_instances.items():
            try:
                uni.shutdown_sync()
            except Exception as e:
                # Log error but continue shutting down other instances
                print(f"Error shutting down uniko instance {cache_key}: {e}")

        self._uniko_instances.clear()

    def __del__(self):
        """Cleanup on garbage collection."""
        self.shutdown()
