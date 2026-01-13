import pytest

from rustic_ai.core.messaging import MessagingConfig


class TestMessagingConfig:
    def test_validate_config(self):
        """
        Test the validate_config method.
        """
        config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )
        config.validate_config()

    def test_validate_config_invalid_backend_module(self):
        config = MessagingConfig(
            backend_module="invalid_module",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

        with pytest.raises(ModuleNotFoundError):
            config.validate_config()

    def test_validate_config_invalid_backend_class(self):
        config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InvalidStorage",
            backend_config={},
        )

        with pytest.raises(AttributeError):
            config.validate_config()

    def test_validate_config_invalid_backend_config(self):
        config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={"invalid_key": "value"},
        )

        with pytest.raises(ValueError):
            config.validate_config()
