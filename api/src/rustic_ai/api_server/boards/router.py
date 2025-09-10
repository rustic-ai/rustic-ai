import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine
from starlette import status

from rustic_ai.api_server.boards.schema import (
    BoardMessagesResponse,
    BoardResponse,
    BoardsResponse,
    CreateBoardRequest,
    PinMessageToBoardRequest,
)
from rustic_ai.api_server.boards.service import BoardService
from rustic_ai.api_server.guilds.schema import IdInfo
from rustic_ai.core.guild.metastore import Metastore

router = APIRouter()
board_service = BoardService()


@router.post(
    "/guilds/{guild_id}/boards",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBoard",
)
def create_board(guild_id: str, board: CreateBoardRequest, engine: Engine = Depends(Metastore.get_engine)):
    """
    Creates a new board for a guild.

    Args:
        guild_id (str): The ID of the guild to create the board for.
        board (CreateBoardRequest): The board creation request.

    Returns:
        IdInfo: The id of the newly created board.
    """
    try:
        board_id = board_service.create_board(engine, guild_id, board)
        logging.debug(f"New board created: {board_id}")
        return IdInfo(id=board_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds/{guild_id}/boards", response_model=BoardsResponse, operation_id="getBoards")
def get_boards(guild_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """
    Retrieves all boards for a guild.

    Args:
        guild_id (str): The ID of the guild to get boards for.

    Returns:
        BoardsResponse: The boards for the guild.
    """
    try:
        boards = board_service.get_boards(engine, guild_id)
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


@router.post("/boards/{board_id}/messages", status_code=status.HTTP_200_OK, operation_id="pinMessageToBoard")
def pin_message_to_board(
    board_id: str,
    request: PinMessageToBoardRequest,
    engine: Engine = Depends(Metastore.get_engine),
):
    """
    Pins a message to a board.

    Args:
        board_id (str): The ID of the board to pin the message to.
        request (PinMessageToBoardRequest): The request containing the message_id.

    Returns:
        dict: Success message.
    """
    try:
        board_service.pin_message_to_board(engine, board_id, request.message_id)
        return {"message": "Message pinned to the board successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/boards/{board_id}/messages",
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
        message_ids = board_service.get_board_message_ids(engine, board_id)
        return BoardMessagesResponse(ids=message_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/boards/{board_id}/messages/{message_id}",
    status_code=status.HTTP_200_OK,
    operation_id="unpinMessageFromBoard",
)
def unpin_message_from_board(board_id: str, message_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """
    Unpins a message from a board.

    Args:
        board_id (str): The ID of the board to unpin the message from.
        message_id (str): The ID of the message to unpin.

    Returns:
        dict: Success message.
    """
    try:
        board_service.unpin_message_from_board(engine, board_id, message_id)
        return {"message": "Message unpinned from the board successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
