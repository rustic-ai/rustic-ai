import asyncio
import gc
import hashlib
import multiprocessing
import os
import socket
import threading
import time
import uuid

import pytest

from rustic_ai.core.guild.dsl import AgentSpec

# Configure multiprocessing early to avoid fork() warnings in multi-threaded test environments
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    # Start method may already be set, which is fine
    pass

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

# Global counter for unique guild IDs
TEST_GUILD_COUNT = 0


@pytest.fixture(scope="session", autouse=True)
def cleanup_aiosqlite():
    """Auto-cleanup fixture that runs after all tests."""
    yield  # Tests run here

    # After all tests, cleanup aiosqlite connections
    try:
        import aiosqlite

        gc.collect()
        connections = [obj for obj in gc.get_objects() if isinstance(obj, aiosqlite.Connection)]

        if connections:
            print(f"\n[Cleanup] Closing {len(connections)} aiosqlite connection(s)...")

            async def close_all():
                for conn in connections:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                await asyncio.sleep(0.5)

            asyncio.run(close_all())
            print("[Cleanup] Done")
    except ImportError:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Report any remaining blocked threads."""
    main_thread = threading.main_thread()
    blocked = [t for t in threading.enumerate() if not t.daemon and t != main_thread]

    if blocked:
        print(f"\n⚠ WARNING: {len(blocked)} thread(s) still blocking:")
        for t in blocked:
            print(f"  - {t.name}")
    else:
        print("\n✓ All threads cleaned up successfully")


def derive_port_from_test_name(test_name: str, start_port: int = 31143) -> int:
    """Derive a unique port number from test name using hash."""
    # Create MD5 hash of test name for good distribution
    hash_obj = hashlib.md5(test_name.encode())
    hash_int = int(hash_obj.hexdigest(), 16)

    # Map to port range (10,000 ports: 31143-41143)
    port_offset = hash_int % 10000
    return start_port + port_offset


def find_working_port(start_port: int, max_attempts: int = 50) -> int:
    """Find an available port starting from start_port with fallback mechanism."""
    for offset in range(max_attempts):
        port = start_port + offset
        try:
            # Quick availability check
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports found starting from {start_port}")


@pytest.fixture(scope="session")
def org_id():
    return "acmeorganizationid"


@pytest.fixture(scope="session")
def messaging_server(request):
    """Start embedded messaging server with test-name-derived port."""
    import asyncio
    import threading
    import time

    from rustic_ai.core.messaging.backend.embedded_backend import EmbeddedServer

    # Get unique port from test name, incorporating worker ID for parallel execution
    test_name = request.node.name or "session"

    # Add worker ID for pytest-xdist parallel execution
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    unique_name = f"{test_name}_{worker_id}"

    base_port = derive_port_from_test_name(unique_name)

    # Find working port with fallback mechanism
    port = find_working_port(base_port)
    print(f"Worker '{worker_id}' test '{test_name}' using port {port} (base: {base_port})")

    server = EmbeddedServer(port=port)

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.start())
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if server.running:
                loop.run_until_complete(server.stop())
            loop.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(1.0)  # Wait for server startup

    yield server, port

    # Cleanup
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
def database(request):
    """Database fixture with test-name-derived filename."""
    # Create filename from test name (sanitize for filesystem)
    test_name = request.node.name.replace(":", "_").replace("[", "_").replace("]", "_").replace("/", "_")

    # Add worker ID for pytest-xdist parallel execution
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    db_file = f"test_rustic_app_{test_name}_{worker_id}.db"
    db = f"sqlite:///{db_file}"

    print(f"Worker '{worker_id}' test '{request.node.name}' using database {db_file}")

    # Clean up any existing database file
    if os.path.exists(db_file):
        os.remove(db_file)

    # Initialize the database properly
    Metastore.initialize_engine(db)
    Metastore.get_engine(db)
    Metastore.create_db()

    yield db

    # Cleanup
    try:
        Metastore.drop_db()
    except Exception:
        # If cleanup fails, just remove the file
        pass
    finally:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except Exception:
            # Ignore file removal errors
            pass


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
def generator():
    return GemstoneGenerator(1)


@pytest.fixture
def probe_spec():
    # Create a unique probe agent for each test to avoid state sharing
    probe_id = f"test_agent_{int(time.time() * 1000000) % 1000000}_{uuid.uuid4().hex[:8]}"

    probe_spec: AgentSpec = (
        AgentBuilder(ProbeAgent)
        .set_id(probe_id)
        .set_name(f"Test Agent {probe_id}")
        .set_description("A test agent")
        .build_spec()
    )

    return probe_spec
