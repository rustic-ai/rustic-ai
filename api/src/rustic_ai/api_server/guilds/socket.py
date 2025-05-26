import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import APIRouter, Depends, FastAPI, WebSocket
from sqlalchemy import Engine

from rustic_ai.api_server.guilds.comms_manager import GuildCommunicationManager
from rustic_ai.api_server.guilds.system_comms_manager import SystemCommunicationManager
from rustic_ai.core.guild.metastore.database import Metastore

socket = APIRouter()


@socket.websocket("/guilds/{guild_id}/usercomms/{user_id}/{user_name}")
async def websocket_endpoint(
    websocket: WebSocket,
    guild_id: str,
    user_id: str,
    user_name: str,
    guild_comm_manager: GuildCommunicationManager = Depends(GuildCommunicationManager.get_instance),
    engine: Engine = Depends(Metastore.get_engine),
):
    logging.info(f"Connecting websocket for guild {guild_id} and user {user_id}")
    logging.info(f"Engine: {engine}")
    await guild_comm_manager.handle_websocket_connection(websocket, guild_id, user_id, user_name, engine)


@socket.websocket("/guilds/{guild_id}/syscomms/{user_id}")
async def system_websocket_endpoint(
    websocket: WebSocket,
    guild_id: str,
    user_id: str,
    system_comm_manager: SystemCommunicationManager = Depends(SystemCommunicationManager.get_instance),
    engine: Engine = Depends(Metastore.get_engine),
):
    logging.info(f"Connecting system updates websocket for guild {guild_id} and user {user_id}")
    logging.info(f"Engine: {engine}")
    await system_comm_manager.handle_websocket_connection(websocket, guild_id, user_id, engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logging.info("Starting communication managers")
        yield
    finally:
        logging.info("Shutting down communication managers")
        await asyncio.gather(
            GuildCommunicationManager.get_instance().shutdown(),
            SystemCommunicationManager.get_instance().shutdown(),
        )
