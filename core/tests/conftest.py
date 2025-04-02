import pytest


@pytest.fixture
def client_properties():
    return {"client_id": "client1", "name": "client1"}
