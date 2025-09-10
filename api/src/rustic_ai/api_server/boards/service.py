from typing import List

from fastapi import HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, select

from rustic_ai.api_server.boards.models import Board, PinnedMessage
from rustic_ai.api_server.boards.schema import CreateBoardRequest
from rustic_ai.core.guild.metastore import GuildModel


class BoardService:

    def create_board(self, engine: Engine, guild_id: str, board: CreateBoardRequest) -> str:
        """
        Creates a new board for a guild.

        Args:
            engine (Engine): The database engine.
            guild_id (str): The ID of the guild to create the board for.
            board (CreateBoardRequest): The board creation request.

        Returns:
            str: The ID of the created board.
        """
        with Session(engine) as session:
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

    def get_boards(self, engine: Engine, guild_id: str) -> List[Board]:
        """
        Retrieves all boards for a guild.

        Args:
            engine (Engine): The database engine.
            guild_id (str): The ID of the guild to get boards for.

        Returns:
            List[Board]: List of boards for the guild.
        """
        with Session(engine) as session:
            guild_model = GuildModel.get_by_id(session, guild_id)
            if guild_model is None:
                raise HTTPException(status_code=404, detail="Guild not found")

            statement = select(Board).where(Board.guild_id == guild_id)
            boards = session.exec(statement).all()

            return list(boards)

    def pin_message_to_board(self, engine: Engine, board_id: str, message_id: str) -> None:
        """
        Pins a message to a board.

        Args:
            engine (Engine): The database engine.
            board_id (str): The ID of the board to pin the message to.
            message_id (str): The ID of the message to pin.
        """
        with Session(engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            existing_entry = session.get(PinnedMessage, (board_id, message_id))
            if existing_entry is not None:
                raise HTTPException(status_code=409, detail="Message already pinned to board")

            pinned_message = PinnedMessage(board_id=board_id, message_id=message_id)
            session.add(pinned_message)
            session.commit()

    def get_board_message_ids(self, engine: Engine, board_id: str) -> List[str]:
        """
        Retrieves all message IDs for a board.

        Args:
            engine (Engine): The database engine.
            board_id (str): The ID of the board to get messages for.

        Returns:
            List[str]: List of message IDs in the board.
        """
        with Session(engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            statement = select(PinnedMessage.message_id).where(PinnedMessage.board_id == board_id)
            message_ids = session.exec(statement).all()

            return list(message_ids)

    def unpin_message_from_board(self, engine: Engine, board_id: str, message_id: str) -> None:
        """
        Unpins a message from a board.

        Args:
            engine (Engine): The database engine.
            board_id (str): The ID of the board to unpin the message from.
            message_id (str): The ID of the message to unpin.
        """
        with Session(engine) as session:
            board = session.get(Board, board_id)
            if board is None:
                raise HTTPException(status_code=404, detail="Board not found")

            pinned_message = session.get(PinnedMessage, (board_id, message_id))
            if pinned_message is None:
                raise HTTPException(status_code=404, detail="Message not pinned to board")

            session.delete(pinned_message)
            session.commit()
