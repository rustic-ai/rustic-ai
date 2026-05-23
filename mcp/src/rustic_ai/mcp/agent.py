import os
from typing import Dict, Optional

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext

from .client import MCPClient
from .models import CallToolRequest, MCPAgentConfig, MCPServerConfig


class MCPAgent(Agent[MCPAgentConfig]):
    """
    Agent that connects to a single MCP server and exposes its capabilities.

    Supports OAuth tokens injected via environment variables. When an OAuth provider
    is configured in the agent registry, tokens are automatically passed as environment
    variables to the MCP server process.

    Example agent registry entry:
        - id: SlackMCPAgent
          class_name: rustic_ai.forge.agents.system.mcp_agent.MCPAgent
          description: MCP agent with Slack OAuth integration
          runtime: uvx
          oauth:
            - provider: slack
              label: SLACK_ACCESS_TOKEN
              scopes: [channels:history, chat:write]
    """

    def __init__(self):
        # Enrich the server config with OAuth tokens from environment
        enriched_config = self._enrich_server_config_with_oauth()
        self._mcp_client: Optional[MCPClient] = MCPClient(enriched_config)

    @property
    def server_config(self) -> MCPServerConfig:
        """Get the MCP server configuration."""
        return self.config.server

    def _enrich_server_config_with_oauth(self) -> MCPServerConfig:
        """
        Enrich the server configuration with OAuth tokens from environment variables.

        OAuth tokens are injected by the Forge runtime when an agent has OAuth providers
        configured in its registry entry. The Go runtime resolves tokens from the keychain
        and sets them as environment variables with the label specified in the OAuth config.

        This method merges those environment variables into the server's env dict so they
        are available to the MCP server process.

        Returns:
            Enriched server configuration with OAuth tokens included in env dict
        """
        # Get a copy of the base server config
        server_config = self.server_config.model_copy(deep=True)

        # Collect OAuth tokens from environment
        oauth_env = self._collect_oauth_tokens_from_environment()

        if oauth_env:
            self.logger.info(
                f"Found {len(oauth_env)} OAuth token(s) in environment, "
                f"adding to MCP server config: {list(oauth_env.keys())}"
            )
            # Merge OAuth tokens into the server's environment
            # Config values take precedence over environment to allow explicit overrides
            merged_env = {**oauth_env, **server_config.env}
            server_config.env = merged_env
        else:
            self.logger.debug("No OAuth tokens found in environment")

        return server_config

    def _collect_oauth_tokens_from_environment(self) -> Dict[str, str]:
        """
        Collect OAuth tokens from environment variables.

        The Forge runtime sets environment variables for OAuth providers based on the
        agent's registry entry. This method scans the environment for common OAuth
        token patterns and returns them as a dictionary.

        Common patterns include:
        - *_TOKEN
        - *_ACCESS_TOKEN
        - *_API_KEY
        - *_SECRET
        - OAUTH_*

        Returns:
            Dictionary of OAuth-related environment variables
        """
        oauth_env = {}

        # Common OAuth token environment variable patterns
        oauth_patterns = (
            '_TOKEN',
            '_ACCESS_TOKEN',
            '_API_KEY',
            '_SECRET',
            'OAUTH_',
        )

        # Scan environment for OAuth-related variables
        for key, value in os.environ.items():
            if any(pattern in key for pattern in oauth_patterns):
                # Skip internal Forge variables
                if key.startswith('FORGE_') or key.startswith('RUSTIC_AI_'):
                    continue
                oauth_env[key] = value

        return oauth_env

    def _ensure_client(self):
        """Ensure the MCP client is initialized."""
        if not self._mcp_client:
            enriched_config = self._enrich_server_config_with_oauth()
            self._mcp_client = MCPClient(enriched_config)

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        """
        Handle a tool call request to the MCP server.

        Args:
            ctx: Processing context containing the CallToolRequest payload
        """
        request = ctx.payload

        # Verify server name matches
        if request.server_name != self.server_config.name:
            self.logger.warning(
                f"Received request for unknown server: {request.server_name}. "
                f"This agent is connected to: {self.server_config.name}"
            )
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="UnsupportedMcpServer",
                    error_message=(
                        f"Unsupported MCP server {request.server_name}. "
                        f"This agent is connected to: {self.server_config.name}"
                    ),
                )
            )
            return

        self._ensure_client()
        if not self._mcp_client:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="MCPClientNotFound",
                    error_message="MCP Client not found!",
                )
            )
            return

        try:
            response = await self._mcp_client.call_tool(request)
            if response.is_error:
                ctx.send_error(
                    ErrorMessage(
                        agent_type=self.get_qualified_class_name(),
                        error_type="ErrorProcessingMCPRequest",
                        error_message=response.error or "Unknown error",
                    )
                )
            else:
                ctx.send(response)
        except Exception as e:
            self.logger.exception("Error calling MCP tool")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="MCPToolCallException",
                    error_message=f"Exception during MCP tool call: {str(e)}",
                )
            )
