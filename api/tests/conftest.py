import os

from fastapi.testclient import TestClient
import pytest

from rustic_ai.api_server import addons, catalog, guilds  # noqa


@pytest.fixture
def client(request):
    from rustic_ai.core.guild.metastore.database import Metastore

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

    from rustic_ai.api_server.main import app

    yield TestClient(app)

    Metastore.drop_db()
