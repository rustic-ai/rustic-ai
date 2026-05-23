"""
Unit tests for MCP Agent OAuth environment variable enrichment.
"""

import os
from unittest.mock import Mock, patch

import pytest

from rustic_ai.mcp.agent import MCPAgent
from rustic_ai.mcp.models import MCPAgentConfig, MCPClientType, MCPServerConfig


@pytest.fixture
def base_config():
    """Base MCP agent configuration without OAuth."""
    return MCPAgentConfig(
        server=MCPServerConfig(
            name="test-mcp",
            type=MCPClientType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-test"],
            env={"CONFIG_VAR": "config_value"},
        )
    )


@pytest.fixture
def mock_agent_with_config(base_config):
    """Create a mock MCP agent with configuration."""
    agent = MCPAgent.__new__(MCPAgent)
    agent.config = base_config
    agent.logger = Mock()
    return agent


def test_collect_oauth_tokens_from_environment_empty(mock_agent_with_config):
    """Test collecting OAuth tokens when none are present."""
    with patch.dict(os.environ, {}, clear=True):
        oauth_env = mock_agent_with_config._collect_oauth_tokens_from_environment()
        assert oauth_env == {}


def test_collect_oauth_tokens_single_token(mock_agent_with_config):
    """Test collecting a single OAuth token."""
    env_vars = {"SLACK_ACCESS_TOKEN": "xoxb-test-token"}

    with patch.dict(os.environ, env_vars, clear=True):
        oauth_env = mock_agent_with_config._collect_oauth_tokens_from_environment()
        assert oauth_env == {"SLACK_ACCESS_TOKEN": "xoxb-test-token"}


def test_collect_oauth_tokens_multiple_tokens(mock_agent_with_config):
    """Test collecting multiple OAuth tokens."""
    env_vars = {
        "SLACK_ACCESS_TOKEN": "xoxb-slack-token",
        "GITHUB_TOKEN": "ghp_github_token",
        "GOOGLE_API_KEY": "google-key",
        "AWS_SECRET": "aws-secret",
        "OAUTH_CUSTOM_TOKEN": "custom-token",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        oauth_env = mock_agent_with_config._collect_oauth_tokens_from_environment()
        assert oauth_env == env_vars


def test_collect_oauth_tokens_excludes_forge_vars(mock_agent_with_config):
    """Test that internal Forge variables are excluded."""
    env_vars = {
        "SLACK_TOKEN": "slack-token",
        "FORGE_DATABASE_URL": "should-be-excluded",
        "RUSTIC_AI_STATE_MANAGER": "should-be-excluded",
        "GITHUB_TOKEN": "github-token",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        oauth_env = mock_agent_with_config._collect_oauth_tokens_from_environment()
        assert oauth_env == {
            "SLACK_TOKEN": "slack-token",
            "GITHUB_TOKEN": "github-token",
        }


def test_enrich_server_config_no_oauth(mock_agent_with_config):
    """Test enriching config when no OAuth tokens are present."""
    with patch.dict(os.environ, {}, clear=True):
        enriched = mock_agent_with_config._enrich_server_config_with_oauth()

        # Config env should remain unchanged
        assert enriched.env == {"CONFIG_VAR": "config_value"}
        assert enriched.name == "test-mcp"
        assert enriched.type == MCPClientType.STDIO


def test_enrich_server_config_with_oauth(mock_agent_with_config):
    """Test enriching config with OAuth tokens from environment."""
    oauth_env = {
        "SLACK_ACCESS_TOKEN": "xoxb-slack-token",
        "GITHUB_TOKEN": "ghp-github-token",
    }

    with patch.dict(os.environ, oauth_env, clear=True):
        enriched = mock_agent_with_config._enrich_server_config_with_oauth()

        # Should contain both OAuth tokens and config vars
        assert enriched.env["SLACK_ACCESS_TOKEN"] == "xoxb-slack-token"
        assert enriched.env["GITHUB_TOKEN"] == "ghp-github-token"
        assert enriched.env["CONFIG_VAR"] == "config_value"
        assert len(enriched.env) == 3


def test_config_overrides_oauth_token(mock_agent_with_config):
    """Test that config values take precedence over OAuth tokens."""
    # Set an OAuth token in environment
    oauth_env = {"SLACK_ACCESS_TOKEN": "oauth-token"}

    # Also set it in config with a different value
    mock_agent_with_config.config.server.env["SLACK_ACCESS_TOKEN"] = "config-override"

    with patch.dict(os.environ, oauth_env, clear=True):
        enriched = mock_agent_with_config._enrich_server_config_with_oauth()

        # Config value should win
        assert enriched.env["SLACK_ACCESS_TOKEN"] == "config-override"


def test_enrich_server_config_logging(mock_agent_with_config):
    """Test that OAuth token enrichment is logged."""
    oauth_env = {
        "SLACK_ACCESS_TOKEN": "token1",
        "GITHUB_TOKEN": "token2",
    }

    with patch.dict(os.environ, oauth_env, clear=True):
        mock_agent_with_config._enrich_server_config_with_oauth()

        # Should log the found tokens
        mock_agent_with_config.logger.info.assert_called_once()
        call_args = mock_agent_with_config.logger.info.call_args[0][0]
        assert "Found 2 OAuth token(s)" in call_args
        assert "SLACK_ACCESS_TOKEN" in call_args
        assert "GITHUB_TOKEN" in call_args


def test_enrich_server_config_no_oauth_logging(mock_agent_with_config):
    """Test logging when no OAuth tokens are found."""
    with patch.dict(os.environ, {}, clear=True):
        mock_agent_with_config._enrich_server_config_with_oauth()

        # Should log debug message
        mock_agent_with_config.logger.debug.assert_called_once_with(
            "No OAuth tokens found in environment"
        )


def test_pattern_matching_variations(mock_agent_with_config):
    """Test various OAuth token naming patterns."""
    env_vars = {
        "SERVICE_TOKEN": "token1",
        "API_ACCESS_TOKEN": "token2",
        "MY_API_KEY": "token3",
        "DB_SECRET": "token4",
        "OAUTH_PROVIDER_KEY": "token5",
        "REGULAR_VAR": "should-not-match",  # Doesn't match any pattern
    }

    with patch.dict(os.environ, env_vars, clear=True):
        oauth_env = mock_agent_with_config._collect_oauth_tokens_from_environment()

        # Should match all except REGULAR_VAR
        assert "SERVICE_TOKEN" in oauth_env
        assert "API_ACCESS_TOKEN" in oauth_env
        assert "MY_API_KEY" in oauth_env
        assert "DB_SECRET" in oauth_env
        assert "OAUTH_PROVIDER_KEY" in oauth_env
        assert "REGULAR_VAR" not in oauth_env


@pytest.mark.asyncio
async def test_agent_initialization_with_oauth(base_config):
    """Test that agent initialization properly enriches config with OAuth."""
    oauth_env = {"SLACK_ACCESS_TOKEN": "xoxb-test-token"}

    with patch.dict(os.environ, oauth_env, clear=True):
        # Create agent without calling __init__
        agent = MCPAgent.__new__(MCPAgent)
        agent.config = base_config
        agent.logger = Mock()

        # Now call __init__ to trigger OAuth enrichment
        agent.__init__()

        # Client should be initialized with enriched config
        assert agent._mcp_client is not None
        assert agent._mcp_client.config.env["SLACK_ACCESS_TOKEN"] == "xoxb-test-token"
        assert agent._mcp_client.config.env["CONFIG_VAR"] == "config_value"
