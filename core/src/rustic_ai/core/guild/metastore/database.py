import logging
import os
from typing import Optional

from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine


class Metastore:
    """
    Metastore class to handle database initialization and engine creation.
    """

    _default_db: str = "sqlite:///rustic_app.db"

    _engine: Optional[Engine] = None

    _database: str = _default_db

    _initialized: bool = False

    @classmethod
    def initialize_engine(cls, db: str = _default_db) -> None:
        """
        Initialize the database and engine.
        """
        if not cls._initialized:
            cls.get_engine(db)
            cls.create_db()
            cls._initialized = True
        else:
            logging.warning("Engine already initialized")  # pragma: no cover

    @classmethod
    def get_engine(cls, sqldb: str = _default_db) -> Engine:
        """
        Initialize the database engine
        """
        if not cls._engine:
            cls._database = sqldb
            cls._engine = create_engine(sqldb)
        return cls._engine

    @classmethod
    def create_db(cls) -> None:
        """
        Create the database.
        """
        if cls._engine:
            SQLModel.metadata.create_all(cls._engine)
        else:
            raise ValueError("Engine not initialized")  # pragma: no cover

    @classmethod
    def get_db_url(cls) -> str:
        """
        Get the database URL.
        """
        return cls._database

    @classmethod
    def drop_db(cls, unsafe=False) -> None:
        """
        Drop the database.
        """
        if cls._engine:
            SQLModel.metadata.drop_all(cls._engine)
            # delete the database
            cls._engine.dispose()
            cls._engine = None
            cls._initialized = False
            # delete the database file if it is sqlite
            if cls._database.startswith("sqlite:///"):  # pragma: no cover
                os.remove(cls._database[10:])

            cls._database = cls._default_db
        elif not unsafe:
            raise ValueError("Engine not initialized")  # pragma: no cover

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the engine is initialized.
        """
        return cls._initialized
