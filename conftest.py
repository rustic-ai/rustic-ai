import gc
import multiprocessing
import os
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
        import asyncio

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


@pytest.fixture(scope="session")
def org_id():
    return "acmeorganizationid"


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
def guild(org_id, database):
    global TEST_GUILD_COUNT
    TEST_GUILD_COUNT += 1
    # Use a unique guild ID that includes timestamp and UUID to ensure complete isolation
    guild_id = f"test_guild_{TEST_GUILD_COUNT}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    # Use InMemoryMessagingBackend as default for tests
    messaging_config: MessagingConfig = MessagingConfig(
        backend_module="rustic_ai.core.messaging.backend",
        backend_class="InMemoryMessagingBackend",
        backend_config={},
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
        # Log but don't fail test cleanup
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
