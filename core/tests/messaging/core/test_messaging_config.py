import pytest

from rustic_ai.core.messaging import MessagingConfig

# Test case to test the MessagingConfig class


class TestMessagingConfig:
    def test_validate_config(self, messaging_server):
        """
        Test the validate_config method.
        """
        server, port = messaging_server
        config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"auto_start_server": False, "port": port},
        )
        config.validate_config()

    def test_validate_config_invalid_backend_module(self, messaging_server):
        server, port = messaging_server
        config = MessagingConfig(
            backend_module="invalid_module",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"auto_start_server": False, "port": port},
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

    def test_validate_config_invalid_backend_config(self, messaging_server):
        server, port = messaging_server
        config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"invalid_key": "value", "port": port},
        )

        with pytest.raises(ValueError):
            config.validate_config()
