import os
from typing import Optional

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.secrets.secret_provider import (
    SecretProvider,
)


class EnvSecretProvider(SecretProvider):
    def __init__(self, guild_id: str, agent_id: str):
        self.guild_id_upper = guild_id.upper()
        self.agent_id_upper = agent_id.upper()

    def get_secret(self, key: str) -> Optional[str]:
        secret = os.getenv(f"{self.guild_id_upper}_{self.agent_id_upper}_{key.upper()}")  # Namespaced to Agent
        if not secret:
            secret = os.getenv(f"{self.guild_id_upper}_{key.upper()}")  # Namespaced to Guild

        if not secret:
            secret = os.getenv(f"{key.upper()}")  # Global secret

        return secret


class EnvSecretProviderDependencyResolver(DependencyResolver[SecretProvider]):
    def __init__(self):
        super().__init__()

    def resolve(self, guild_id: str, agent_id: str) -> SecretProvider:
        return EnvSecretProvider(guild_id, agent_id)
