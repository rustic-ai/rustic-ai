import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine
from starlette import status

from rustic_ai.api_server.addons.boards.board_store import BoardStore
from rustic_ai.api_server.addons.boards.schema import (
    AddMessageToBoardRequest,
    BoardMessagesResponse,
    BoardResponse,
    BoardsResponse,
    CreateBoardRequest,
)
from rustic_ai.api_server.guilds.schema import IdInfo
from rustic_ai.core.guild.metastore import Metastore

boards_router = APIRouter()


@boards_router.post(
    "/",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBoard",
)
def create_board(board: CreateBoardRequest, engine: Engine = Depends(Metastore.get_engine)):
    """
    Creates a new board for a guild.

    Args:
        guild_id (str): The ID of the guild to create the board for.
        board (CreateBoardRequest): The board creation request.

    Returns:
        IdInfo: The id of the newly created board.
    """
    try:
        board_store = BoardStore(engine)
        board_id = board_store.create_board(board.guild_id, board)
        logging.debug(f"New board created: {board_id}")
        return IdInfo(id=board_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@boards_router.get("/", response_model=BoardsResponse, operation_id="getBoards")
def get_boards(guild_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """
    Retrieves all boards for a guild.

    Args:
        guild_id (str): The ID of the guild to get boards for.

    Returns:
        BoardsResponse: The boards for the guild.
    """
    try:
        board_store = BoardStore(engine)
        boards = board_store.get_boards(guild_id)
        board_responses = [
            BoardResponse(
                id=board.id,
                name=board.name,
                guild_id=board.guild_id,
                created_by=board.created_by,
                created_at=board.created_at,
                is_default=board.is_default,
                is_private=board.is_private,
            )
            for board in boards
        ]
        return BoardsResponse(boards=board_responses)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@boards_router.post("/{board_id}/messages", status_code=status.HTTP_200_OK, operation_id="addMessageToBoard")
def add_message_to_board(
    board_id: str,
    request: AddMessageToBoardRequest,
    engine: Engine = Depends(Metastore.get_engine),
):
    """
    Adds a message to a board.

    Args:
        board_id (str): The ID of the board to add the message to.
        request (AddMessageToBoardRequest): The request containing the message_id.

    Returns:
        dict: Success message.
    """
    try:
        board_store = BoardStore(engine)
        board_store.add_message_to_board(board_id, request.message_id)
        return {"message": "Message added to the board successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@boards_router.get(
    "/{board_id}/messages",
    response_model=BoardMessagesResponse,
    operation_id="getBoardMessageIds",
)
def get_board_messages(board_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """
    Retrieves all message IDs for a board.

    Args:
        board_id (str): The ID of the board to get messages for.

    Returns:
        BoardMessagesResponse: The message IDs in the board.
    """
    try:
        board_store = BoardStore(engine)
        message_ids = board_store.get_board_message_ids(board_id)
        return BoardMessagesResponse(ids=message_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@boards_router.delete(
    "/{board_id}/messages/{message_id}",
    status_code=status.HTTP_200_OK,
    operation_id="removeMessageFromBoard",
)
def remove_message_from_board(board_id: str, message_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """
    Removes a message from a board.

    Args:
        board_id (str): The ID of the board to remove the message from.
        message_id (str): The ID of the message to remove.

    Returns:
        dict: Success message.
    """
    try:
        board_store = BoardStore(engine)
        board_store.remove_message_from_board(board_id, message_id)
        return {"message": "Message removed from the board successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
