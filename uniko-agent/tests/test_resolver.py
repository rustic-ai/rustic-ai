"""Unit tests for UnikoResolver LLM spec building."""

import os
from unittest.mock import patch

import pytest
import uniko

from rustic_ai.uniko_agent.resolver import UnikoResolver


class TestUnikoResolverLLMSpec:
    """Tests for UnikoResolver LLM specification building."""

    def test_generic_native_provider_preserves_options(self):
        options = {"temperature": 0.2}
        with patch("uniko.models.inputs._native") as get_native:
            native = get_native.return_value.LlmSpec
            llm = UnikoResolver()._build_llm_spec(
                {
                    "provider": "generic",
                    "provider_id": "remote/anthropic",
                    "alias": "answer/custom",
                    "model_id": "claude-sonnet",
                    "options": options,
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
            )
        native.new.assert_called_once_with(
            "answer/custom", "remote/anthropic", "claude-sonnet", options, "ANTHROPIC_API_KEY"
        )
        assert llm is native.new.return_value

    def test_build_llm_spec_openai_basic(self):
        """Test building OpenAI LLM spec with minimal config."""
        resolver = UnikoResolver()

        spec = {"alias": "openai", "model_id": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            # Should return a uniko.LlmSpec object
            assert llm is not None
            # The object should have the correct type from uniko
            assert hasattr(llm, "__class__")

    def test_build_llm_spec_openai_with_base_url(self):
        """Test building OpenAI LLM spec with custom base URL."""
        resolver = UnikoResolver()

        spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY",
            "base_url": "http://localhost:8080/v1",
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_openai_default_key_env(self):
        """Test that OPENAI_API_KEY is used as default key_env."""
        resolver = UnikoResolver()

        spec = {"alias": "openai", "model_id": "gpt-4o-mini"}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    @pytest.mark.parametrize("alias", ["mistral", "mistralrs"])
    def test_removed_embedded_runtime_is_rejected(self, alias):
        with pytest.raises(ValueError, match="embedded mistralrs runtime is no longer supported"):
            UnikoResolver()._build_llm_spec({"alias": alias, "model_id": "some-model"})

    @pytest.mark.parametrize(
        "provider, extras, method, arguments",
        [
            ("openai", {}, "openai", ("answer/custom", "custom-model", None)),
            (
                "openai_with_key_env",
                {"key_env": "CUSTOM_KEY", "base_url": "https://example.com/v1"},
                "openai_with_key_env",
                ("answer/custom", "custom-model", "CUSTOM_KEY", "https://example.com/v1"),
            ),
            (
                "llamacpp",
                {"base_url": "http://localhost:8080/v1"},
                "llamacpp",
                ("answer/custom", "custom-model", "http://localhost:8080/v1", None),
            ),
            (
                "llamacpp",
                {"base_url": "http://localhost:8080/v1", "key_env": "SERVER_KEY"},
                "llamacpp",
                ("answer/custom", "custom-model", "http://localhost:8080/v1", "SERVER_KEY"),
            ),
        ],
    )
    def test_native_llm_modes_preserve_alias_and_model(self, provider, extras, method, arguments):
        with patch("uniko.models.inputs._native") as get_native:
            native = get_native.return_value.LlmSpec
            llm = UnikoResolver()._build_llm_spec(
                {"provider": provider, "alias": "answer/custom", "model_id": "custom-model", **extras}
            )
        getattr(native, method).assert_called_once_with(*arguments)
        assert llm is getattr(native, method).return_value

    @pytest.mark.parametrize(
        "spec, error",
        [
            ({"provider": "llamacpp", "alias": "answer/local", "model_id": "qwen"}, "base_url"),
            ({"provider": "mistralrs", "alias": "answer/local", "model_id": "model"}, "provider"),
            ({"provider": "openai", "alias": "answer/api", "model_id": "model", "typo": True}, "typo"),
        ],
    )
    def test_invalid_native_llm_configuration(self, spec, error):
        with pytest.raises(ValueError, match=error):
            UnikoResolver()._build_llm_spec(spec)

    def test_build_llm_spec_unsupported_alias(self):
        """Test that unsupported alias raises ValueError."""
        resolver = UnikoResolver()

        spec = {"alias": "unsupported_provider", "model_id": "some-model"}

        with pytest.raises(ValueError, match="Unsupported LLM alias"):
            resolver._build_llm_spec(spec)

    def test_build_llm_spec_default_alias(self):
        """Test that 'openai' is used as default alias."""
        resolver = UnikoResolver()

        spec = {"model_id": "gpt-4o-mini"}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None

    def test_build_llm_spec_default_model_id(self):
        """Test that 'gpt-4o-mini' is used as default model_id."""
        resolver = UnikoResolver()

        spec = {"alias": "openai"}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = resolver._build_llm_spec(spec)
            assert llm is not None


class TestUnikoResolverIntegration:
    """Integration tests for UnikoResolver with LLM configuration."""

    def test_resolver_with_llm_spec(self):
        """Test that resolver can be instantiated with LLM spec."""
        llm_spec = {"alias": "openai", "model_id": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"}

        resolver = UnikoResolver(storage_path=None, llm_spec=llm_spec, streaming=False)

        assert resolver.llm_spec == llm_spec
        assert resolver.streaming is False

    def test_resolver_without_llm_spec(self):
        """Test that resolver works without LLM spec (None)."""
        resolver = UnikoResolver(storage_path=None, llm_spec=None, streaming=False)

        assert resolver.llm_spec is None

    def test_resolver_with_storage_path(self):
        """Storage paths are locations within the injected agent filesystem."""
        resolver = UnikoResolver(storage_path="memory", llm_spec=None)

        assert resolver.storage_path == "memory"

    def test_resolver_builds_uniko_instance_with_llm(self):
        """Test that resolver can build a complete Uniko instance with LLM spec."""
        llm_spec = {"alias": "openai", "model_id": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"}

        resolver = UnikoResolver(storage_path=None, llm_spec=llm_spec, streaming=False)

        # Mock environment variable
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            # This should build successfully without raising the alias format error
            agent = resolver.resolve(org_id="test-org", guild_id="test-guild", agent_id="test-agent")
            assert agent is not None

            # Cleanup
            resolver.shutdown()


class TestUnikoResolverModelConfiguration:
    def test_native_builder_applies_config_and_model_overrides(self):
        resolver = UnikoResolver(
            config={"recall_limit": 8, "embedding": {"model_id": "BGESmallENV15"}},
            embedding="minilm",
            nlp="v1",
            reranker=False,
        )
        agent = resolver.resolve("org", "guild", "agent")
        instance = resolver._uniko_instances["org:guild:agent"]
        config = instance.config()
        assert config["recall_limit"] == 8
        assert config["embedding"]["model_id"] == "AllMiniLML6V2"
        assert config["reranker"]["enabled"] is False
        del agent
        resolver.shutdown()

    @pytest.mark.parametrize(
        "options",
        [
            {"config": {"misspelled_option": True}},
            {"embedding": "unknown-preset"},
            {"nlp": "unknown-preset"},
            {"reranker": "unknown-preset"},
        ],
    )
    def test_native_validation_rejects_invalid_configuration(self, options):
        with pytest.raises(uniko.ConfigError, match="unknown"):
            UnikoResolver(**options).resolve("org", "guild", "agent")
