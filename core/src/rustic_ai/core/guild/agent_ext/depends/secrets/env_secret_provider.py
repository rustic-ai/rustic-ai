import os
from typing import Optional

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.secrets.secret_provider import (
    SecretProvider,
)


class EnvSecretProvider(SecretProvider):
    def __init__(self, org_id: str, guild_id: str, agent_id: str):
        self.org_id_upper = org_id.upper()
        self.guild_id_upper = guild_id.upper()
        self.agent_id_upper = agent_id.upper()

    def get_secret(self, key: str) -> Optional[str]:
        key_upper = key.upper()
        # Namespaced to Agent
        secret = os.getenv(f"{self.org_id_upper}_{self.guild_id_upper}_{self.agent_id_upper}_{key_upper}")
        if not secret:
            # Namespaced to Guild
            secret = os.getenv(f"{self.org_id_upper}_{self.guild_id_upper}_{key_upper}")
        if not secret:
            # Namespaced to Org
            secret = os.getenv(f"{self.org_id_upper}_{key_upper}")
        if not secret:
            # Global secret
            secret = os.getenv(key_upper)

        return secret


class EnvSecretProviderDependencyResolver(DependencyResolver[SecretProvider]):
    def __init__(self):
        super().__init__()

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> SecretProvider:
        return EnvSecretProvider(org_id, guild_id, agent_id)
