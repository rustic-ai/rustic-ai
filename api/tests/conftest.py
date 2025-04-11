import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from rustic_ai.core.guild.metastore.database import Metastore

    rustic_metastore = "sqlite:///guild_test_rustic_app.db"
    Metastore.initialize_engine(rustic_metastore)

    from rustic_ai.api_server.main import app

    yield TestClient(app)

    Metastore.drop_db()
