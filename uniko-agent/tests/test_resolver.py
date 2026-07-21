"""Unit tests for UnikoResolver LLM spec building."""

import os
from unittest.mock import patch

import pytest

from rustic_ai.uniko_agent.resolver import UnikoResolver


class TestUnikoResolverLLMSpec:
    """Tests for UnikoResolver LLM specification building."""

    def test_build_llm_spec_openai_basic(self):
        """Test building OpenAI LLM spec with minimal config."""
        resolver = UnikoResolver()

        spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            # Should return a uniko.LlmSpec object
            assert llm is not None
            # The object should have the correct type from uniko
            assert hasattr(llm, '__class__')

    def test_build_llm_spec_openai_with_base_url(self):
        """Test building OpenAI LLM spec with custom base URL."""
        resolver = UnikoResolver()

        spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY",
            "base_url": "http://localhost:8080/v1"
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_openai_default_key_env(self):
        """Test that OPENAI_API_KEY is used as default key_env."""
        resolver = UnikoResolver()

        spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini"
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_mistral(self):
        """Test building Mistral LLM spec."""
        resolver = UnikoResolver()

        spec = {
            "alias": "mistral",
            "model_id": "mistral-large",
            "key_env": "MISTRAL_API_KEY"
        }

        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_unsupported_alias(self):
        """Test that unsupported alias raises ValueError."""
        resolver = UnikoResolver()

        spec = {
            "alias": "unsupported_provider",
            "model_id": "some-model"
        }

        with pytest.raises(ValueError, match="Unsupported LLM alias"):
            resolver._build_llm_spec(spec)

    def test_build_llm_spec_default_alias(self):
        """Test that 'openai' is used as default alias."""
        resolver = UnikoResolver()

        spec = {
            "model_id": "gpt-4o-mini"
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_default_model_id(self):
        """Test that 'gpt-4o-mini' is used as default model_id."""
        resolver = UnikoResolver()

        spec = {
            "alias": "openai"
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None


class TestUnikoResolverIntegration:
    """Integration tests for UnikoResolver with LLM configuration."""

    def test_resolver_with_llm_spec(self):
        """Test that resolver can be instantiated with LLM spec."""
        llm_spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        }

        resolver = UnikoResolver(
            storage_path=None,
            llm_spec=llm_spec,
            streaming=False
        )

        assert resolver.llm_spec == llm_spec
        assert resolver.streaming is False

    def test_resolver_without_llm_spec(self):
        """Test that resolver works without LLM spec (None)."""
        resolver = UnikoResolver(
            storage_path=None,
            llm_spec=None,
            streaming=False
        )

        assert resolver.llm_spec is None

    def test_resolver_with_storage_path(self):
        """Test resolver with storage path and org/guild level flags."""
        resolver = UnikoResolver(
            storage_path="./data",
            org_level=True,
            guild_level=True,
            llm_spec=None
        )

        assert resolver.storage_path == "./data"
        assert resolver.org_level is True
        assert resolver.guild_level is True

    def test_resolver_builds_uniko_instance_with_llm(self):
        """Test that resolver can build a complete Uniko instance with LLM spec."""
        llm_spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        }

        resolver = UnikoResolver(
            storage_path=None,
            llm_spec=llm_spec,
            streaming=False
        )

        # Mock environment variable
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            # This should build successfully without raising the alias format error
            agent = resolver.resolve(
                org_id="test-org",
                guild_id="test-guild",
                agent_id="test-agent"
            )
            assert agent is not None

            # Cleanup
            resolver.shutdown()
