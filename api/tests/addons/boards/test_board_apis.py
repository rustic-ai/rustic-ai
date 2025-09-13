import json

import pytest

from rustic_ai.api_server.guilds.schema import LaunchGuildReq
from rustic_ai.core.guild.dsl import GuildSpec


@pytest.fixture
def guild_id(client, org_id):
    """Create a test guild and return its ID."""
    guild_spec = GuildSpec(
        name="TestGuild",
        description="A guild for board testing",
        properties={
            "storage": {
                "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                "properties": {},
            }
        },
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    json_data = req.model_dump_json()
    data = json.loads(json_data)

    response = client.post("/api/guilds", json=data, headers={"Content-Type": "application/json"})
    assert response.status_code == 201
    return response.json()["id"]


class TestCreateBoard:
    def test_create_board(self, client, guild_id):
        """Test creating a board with basic fields only."""
        data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_456"}
        response = client.post("/addons/boards/", json=data)

        assert response.status_code == 201
        json_response = response.json()
        assert "id" in json_response


class TestGetBoards:
    def test_get_boards_empty(self, client, guild_id):
        """Test getting boards when none exist."""
        response = client.get(f"/addons/boards?guild_id={guild_id}")

        assert response.status_code == 200
        json_response = response.json()
        assert json_response["boards"] == []

    def test_get_boards_with_multiple(self, client, guild_id):
        """Test getting multiple boards with different flag combinations."""
        board1_data = {"guild_id": guild_id, "name": "Basic Board", "created_by": "user_123"}
        board2_data = {"guild_id": guild_id, "name": "Default Board", "created_by": "user_456", "is_default": True}
        board3_data = {"guild_id": guild_id, "name": "Private Board", "created_by": "user_789", "is_private": True}

        client.post("/addons/boards/", json=board1_data)
        client.post("/addons/boards/", json=board2_data)
        client.post("/addons/boards/", json=board3_data)

        response = client.get(f"/addons/boards?guild_id={guild_id}")

        assert response.status_code == 200
        json_response = response.json()
        boards = json_response["boards"]
        assert len(boards) == 3

        for board in boards:
            assert "is_default" in board
            assert "is_private" in board
            assert isinstance(board["is_default"], bool)
            assert isinstance(board["is_private"], bool)

        board_by_name = {b["name"]: b for b in boards}
        assert board_by_name["Basic Board"]["is_default"] is False
        assert board_by_name["Basic Board"]["is_private"] is False
        assert board_by_name["Default Board"]["is_default"] is True
        assert board_by_name["Default Board"]["is_private"] is False
        assert board_by_name["Private Board"]["is_default"] is False
        assert board_by_name["Private Board"]["is_private"] is True

    def test_get_boards_invalid_guild(self, client):
        """Test getting boards for non-existent guild."""
        response = client.get("/addons/boards?guild_id=invalid-guild-id")

        assert response.status_code == 404
        assert "Guild not found" in response.json()["detail"]


class TestAddMessageToBoard:
    def test_add_message_to_board(self, client, guild_id):
        """Test adding message to board."""
        board_data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json=board_data)
        board_id = board_response.json()["id"]

        message_data = {"message_id": "msg_123"}

        response = client.post(f"/addons/boards/{board_id}/messages", json=message_data)

        assert response.status_code == 200
        assert response.json()["message"] == "Message added to the board successfully"

    def test_add_different_message(self, client, guild_id):
        """Test adding a different message to board."""
        board_data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json=board_data)
        board_id = board_response.json()["id"]

        message_data = {"message_id": "msg_456"}

        response = client.post(f"/addons/boards/{board_id}/messages", json=message_data)

        assert response.status_code == 200

    def test_add_duplicate_message(self, client, guild_id):
        """Test adding duplicate message to board."""
        board_data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json=board_data)
        board_id = board_response.json()["id"]

        message_data = {"message_id": "msg_duplicate"}

        client.post(f"/addons/boards/{board_id}/messages", json=message_data)

        response = client.post(f"/addons/boards/{board_id}/messages", json=message_data)

        assert response.status_code == 409
        assert "Message already added to board" in response.json()["detail"]

    def test_add_message_invalid_board(self, client):
        """Test adding message to non-existent board."""
        message_data = {"message_id": "msg_123"}

        response = client.post("/addons/boards/invalid-id/messages", json=message_data)

        assert response.status_code == 404
        assert "Board not found" in response.json()["detail"]


class TestGetBoardMessages:
    def test_get_messages_empty_board(self, client, guild_id):
        """Test getting messages from empty board."""
        board_data = {"name": "Empty Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json={"guild_id": guild_id, **board_data})
        board_id = board_response.json()["id"]

        response = client.get(f"/addons/boards/{board_id}/messages")

        assert response.status_code == 200
        json_response = response.json()
        assert json_response["ids"] == []

    def test_get_messages_with_content(self, client, guild_id):
        """Test getting messages from board with content."""
        board_data = {"name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json={"guild_id": guild_id, **board_data})
        board_id = board_response.json()["id"]

        # Board messages
        message_ids = ["msg_001", "msg_002", "msg_003"]
        for msg_id in message_ids:
            client.post(f"/addons/boards/{board_id}/messages", json={"message_id": msg_id})

        response = client.get(f"/addons/boards/{board_id}/messages")

        assert response.status_code == 200
        json_response = response.json()
        returned_ids = json_response["ids"]
        assert len(returned_ids) == 3
        assert set(returned_ids) == set(message_ids)


class TestRemoveMessageFromBoard:
    def test_remove_message(self, client, guild_id):
        """Test removing message from board successfully."""
        board_data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json=board_data)
        board_id = board_response.json()["id"]

        message_data = {"message_id": "msg_to_remove"}
        client.post(f"/addons/boards/{board_id}/messages", json=message_data)

        response = client.delete(f"/addons/boards/{board_id}/messages/msg_to_remove")

        assert response.status_code == 200
        assert response.json()["message"] == "Message removed from the board successfully"

        # Verify message is removed
        get_response = client.get(f"/addons/boards/{board_id}/messages")
        assert get_response.json()["ids"] == []

    def test_remove_message_not_on_board(self, client, guild_id):
        """Test removing message that doesn't exist on board."""
        board_data = {"guild_id": guild_id, "name": "Test Board", "created_by": "user_123"}
        board_response = client.post("/addons/boards/", json=board_data)
        board_id = board_response.json()["id"]

        response = client.delete(f"/addons/boards/{board_id}/messages/nonexistent_msg")

        assert response.status_code == 404
        assert "Message not found on board" in response.json()["detail"]
