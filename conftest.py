import os
import time
import uuid

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

TEST_GUILD_COUNT: int = 0


@pytest.fixture(scope="session")
def org_id():
    return "acmeorganizationid"


@pytest.fixture(scope="session")
def messaging_server():
    """Start a single embedded messaging server for all tests in this session."""
    import asyncio
    import threading
    import time

    from rustic_ai.core.messaging.backend.embedded_backend import EmbeddedServer

    port = 31143  # Use unique port for conftest tests
    server = EmbeddedServer(port=port)

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.start())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(server.stop())
            loop.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(1.0)  # Wait for server to start

    yield server, port

    # Clean up
    if server.running:
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()


@pytest.fixture(autouse=True)
def cleanup_messaging_server_state(messaging_server):
    """Auto-use fixture that cleans up server state before each test."""
    server, port = messaging_server
    # Clear server state before each test
    server.topics.clear()
    server.messages.clear()
    server.subscribers.clear()
    yield
    # Clean up after test as well
    server.topics.clear()
    server.messages.clear()
    server.subscribers.clear()


@pytest.fixture
def database():
    """Database fixture that properly initializes the database for tests."""
    db = "sqlite:///test_rustic_app.db"
    
    # Clean up any existing database file
    if os.path.exists("test_rustic_app.db"):
        os.remove("test_rustic_app.db")
    
    # Initialize the database properly
    Metastore.initialize_engine(db)
    Metastore.get_engine(db)
    Metastore.create_db()
    
    yield db
    
    # Clean up after test
    try:
        Metastore.drop_db()
    except Exception:
        # If cleanup fails, just remove the file
        if os.path.exists("test_rustic_app.db"):
            os.remove("test_rustic_app.db")


@pytest.fixture
def guild(org_id, database, messaging_server):
    global TEST_GUILD_COUNT
    TEST_GUILD_COUNT += 1
    # Use a unique guild ID that includes timestamp and UUID to ensure complete isolation
    guild_id = f"test_guild_{TEST_GUILD_COUNT}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    # Use the shared messaging server instead of auto-starting one
    server, messaging_port = messaging_server

    messaging_config: MessagingConfig = MessagingConfig(
        backend_module="rustic_ai.core.messaging.backend.embedded_backend",
        backend_class="EmbeddedMessagingBackend",
        backend_config={
            "auto_start_server": False,  # Connect to existing server
            "port": messaging_port,
        },
    )

    # Create and return a Guild
    guild = Guild(
        id=guild_id,
        name=f"Test Guild {TEST_GUILD_COUNT}",
        description=f"A test guild {guild_id}",
        execution_engine_clz=SyncExecutionEngine.get_qualified_class_name(),
        messaging_config=messaging_config,
        organization_id=org_id,
    )

    yield guild

    # Thorough cleanup to ensure test isolation
    try:
        # Just shutdown the guild - it will handle agent cleanup internally
        # Don't try to remove agents individually as that causes async/sync issues
        guild.shutdown()

        # Give some time for async cleanup
        time.sleep(0.2)

    except Exception:
        # Log but don't fail test cleanup - this is expected during teardown
        # The EmbeddedMessagingBackend async cleanup can cause harmless warnings
        pass


@pytest.fixture
def probe_agent(generator):
    # Create a unique probe agent for each test to avoid state sharing
    probe_id = f"test_agent_{int(time.time() * 1000000) % 1000000}_{uuid.uuid4().hex[:8]}"

    probe: ProbeAgent = (
        AgentBuilder(ProbeAgent)
        .set_id(probe_id)
        .set_name(f"Test Agent {probe_id}")
        .set_description("A test agent")
        .build()
    )

    # Initialize the ID generator that ProbeAgent needs for publishing messages
    probe._set_generator(generator)

    # Clear any previous state
    probe.clear_messages()

    yield probe

    # Cleanup probe agent state
    try:
        probe.clear_messages()
        # Reset any other state that might persist
        if hasattr(probe, "_client") and probe._client:
            try:
                # Properly disconnect the client if it exists
                probe._client.disconnect()
            except Exception as e:
                # Log but don't fail test cleanup
                print(f"Warning: Error disconnecting probe agent client: {e}")
    except Exception as e:
        # Log but don't fail test cleanup
        print(f"Warning: Error during probe agent cleanup: {e}")


@pytest.fixture
def generator() -> GemstoneGenerator:
    """
    Fixture that returns a GemstoneGenerator instance with a seed of 1.
    """
    return GemstoneGenerator(1)
