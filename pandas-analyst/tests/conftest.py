"""
Pytest configuration and fixtures for pandas-data-analyst tests.
"""

import gc
import multiprocessing
import os
import shutil
import tempfile
import threading
import time
import uuid

import pytest

from pydantic import BaseModel

from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority

# Configure multiprocessing early to avoid fork() warnings
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    pass


@pytest.fixture(scope="session", autouse=True)
def cleanup_resources():
    """Cleanup fixture that runs after all tests."""
    yield
    gc.collect()


def pytest_sessionfinish(session, exitstatus):
    """Report any remaining blocked threads."""
    main_thread = threading.main_thread()
    blocked = [t for t in threading.enumerate() if not t.daemon and t != main_thread]
    if blocked:
        print(f"\n[Warning] {len(blocked)} thread(s) still running")


@pytest.fixture(scope="session")
def org_id():
    """Organization ID for test guilds."""
    return "pandas_data_analyst_test_org"


@pytest.fixture
def generator() -> GemstoneGenerator:
    """Gemstone ID generator for creating message IDs."""
    return GemstoneGenerator(1)


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory with sample CSV data for testing."""
    tmpdir = tempfile.mkdtemp()

    # Create a sample CSV file
    data_path = os.path.join(tmpdir, "sales_data.csv")
    with open(data_path, "w") as f:
        f.write("id,product,quantity,price,category\n")
        f.write("1,Apple,50,1.50,Fruit\n")
        f.write("2,Banana,30,0.75,Fruit\n")
        f.write("3,Carrot,25,0.50,Vegetable\n")
        f.write("4,Orange,40,1.25,Fruit\n")
        f.write("5,Broccoli,15,1.00,Vegetable\n")

    # Create employee data
    employees_path = os.path.join(tmpdir, "employees.csv")
    with open(employees_path, "w") as f:
        f.write("id,name,department,salary\n")
        f.write("1,Alice,Engineering,75000\n")
        f.write("2,Bob,Marketing,60000\n")
        f.write("3,Charlie,Engineering,80000\n")
        f.write("4,Diana,Sales,55000\n")
        f.write("5,Eve,Engineering,90000\n")

    yield tmpdir

    shutil.rmtree(tmpdir)


@pytest.fixture
def build_message_from_payload():
    """Factory fixture to build Message objects from payloads."""

    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
    ) -> Message:
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )
        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else "raw_json",
        )

    return _build_message_from_payload


@pytest.fixture
def probe_spec():
    """Create a unique probe agent spec for each test."""
    from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
    from rustic_ai.core.guild.builders import AgentBuilder

    probe_id = f"probe_{int(time.time() * 1000000) % 1000000}_{uuid.uuid4().hex[:8]}"
    return (
        AgentBuilder(ProbeAgent)
        .set_id(probe_id)
        .set_name(f"Test Probe Agent {probe_id}")
        .set_description("A probe agent for testing")
        .build_spec()
    )


@pytest.fixture
def database(request):
    """Database fixture for tests requiring persistence."""
    from rustic_ai.core.guild.metastore.database import Metastore

    test_name = request.node.name.replace(":", "_").replace("[", "_").replace("]", "_").replace("/", "_")
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    db_file = f"test_pandas_analyst_{test_name}_{worker_id}.db"
    db = f"sqlite:///{db_file}"

    if os.path.exists(db_file):
        os.remove(db_file)

    Metastore.initialize_engine(db)
    Metastore.get_engine(db)
    Metastore.create_db()

    yield db

    try:
        Metastore.drop_db()
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except Exception:
            pass
