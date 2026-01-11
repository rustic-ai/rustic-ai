from typing import List

from fastapi import HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, select

from rustic_ai.api_server.addons.boards.models import Board, BoardMessage
from rustic_ai.api_server.addons.boards.schema import CreateBoardRequest
from rustic_ai.core.guild.metastore import GuildModel


class BoardStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_board(self, guild_id: str, board: CreateBoardRequest) -> str:
        """
        Creates a new board for a guild.

        Args:
            guild_id (str): The ID of the guild to create the board for.
            board (CreateBoardRequest): The board creation request.

        Returns:
            str: The ID of the created board.
        """
        with Session(self.engine) as session:
            guild_model = GuildModel.get_by_id(session, guild_id)
            if guild_model is None:
                raise HTTPException(status_code=404, detail="Guild not found")

            board_model = Board(
                name=board.name,
                guild_id=guild_id,
                created_by=board.created_by,
                is_default=board.is_default,
                is_private=board.is_private,
            )
            session.add(board_model)
            session.commit()
            session.refresh(board_model)

            return board_model.id

    def get_boards(self, guild_id: str) -> List[Board]:
        """
        Retrieves all boards for a guild.

        Args:
            guild_id (str): The ID of the guild to get boards for.

        Returns:
            List[Board]: List of boards for the guild.
        """
        with Session(self.engine) as session:
            guild_model = GuildModel.get_by_id(session, guild_id)
            if guild_model is None:
                raise HTTPException(status_code=404, detail="Guild not found")

            statement = select(Board).where(Board.guild_id == guild_id)
            boards = session.exec(statement).all()

            return list(boards)

    def add_message_to_board(self, board_id: str, message_id: str) -> None:
        """
        Adds a message to a board.

        Args:
            board_id (str): The ID of the board to add the message to.
            message_id (str): The ID of the message to add.
        """
        with Session(self.engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            existing_entry = session.get(BoardMessage, (board_id, message_id))
            if existing_entry is not None:
                raise HTTPException(status_code=409, detail="Message already added to board")

            board_message = BoardMessage(board_id=board_id, message_id=message_id)
            session.add(board_message)
            session.commit()

    def get_board_message_ids(self, board_id: str) -> List[str]:
        """
        Retrieves all message IDs for a board.

        Args:
            board_id (str): The ID of the board to get messages for.

        Returns:
            List[str]: List of message IDs in the board.
        """
        with Session(self.engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            statement = select(BoardMessage.message_id).where(BoardMessage.board_id == board_id)
            message_ids = session.exec(statement).all()

            return list(message_ids)

    def remove_message_from_board(self, board_id: str, message_id: str) -> None:
        """
        Removes a message from a board.

        Args:
            board_id (str): The ID of the board to remove the message from.
            message_id (str): The ID of the message to remove.
        """
        with Session(self.engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            board_message = session.get(BoardMessage, (board_id, message_id))
            if board_message is None:
                raise HTTPException(status_code=404, detail="Message not found on board")

            session.delete(board_message)
            session.commit()
