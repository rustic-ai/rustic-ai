import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
import ray
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
import uvicorn

from rustic_ai.api_server import addons, catalog, guilds
from rustic_ai.api_server.guilds.socket import lifespan
from rustic_ai.api_server.logging import LOGGING_CONFIG, RusticLogFormatter
from rustic_ai.core.guild.metastore.database import Metastore

logging_level = os.environ.get("RUSTIC_LOGGING_LEVEL", "DEBUG")
formatter = RusticLogFormatter()

ch = logging.StreamHandler()
ch.setFormatter(formatter)

logging.basicConfig(
    level=logging_level,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[ch],
)

INITIALIZE_RAY_CLUSTER = os.environ.get("RUSTIC_INIT_RAY_CLUSTER", "False").lower() == "true"
LAUNCH_RAY_DASHBOARD = os.environ.get("RUSTIC_LAUNCH_RAY_DASHBOARD", "False").lower() == "true"

if INITIALIZE_RAY_CLUSTER:

    logging.info("Initializing Ray cluster")
    ray.init(include_dashboard=LAUNCH_RAY_DASHBOARD, log_to_driver=False, dashboard_host="0.0.0.0")
    logging.info("Ray cluster initialized")
    logging.info("Ray cluster details: {}".format(ray.get_runtime_context()))

if not Metastore.is_initialized():
    rustic_metastore = os.environ.get("RUSTIC_METASTORE", "sqlite:///rustic_app.db")
    Metastore.initialize_engine(rustic_metastore)
app = FastAPI(title="Rustic AI API", lifespan=lifespan)
app.include_router(guilds.router, prefix="/api")
app.include_router(guilds.socket, prefix="/ws")
app.include_router(catalog.catalog_router, prefix="/catalog")
app.include_router(addons.addons_router, prefix="/addons")


origins = [
    os.environ.get("RUSTIC_CORS_ORIGIN", "http://localhost:3000"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
)


@app.get("/__health")
def health_check():
    return {"message": "All is well"}


@app.exception_handler(StarletteHTTPException)
async def global_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Global exception handler function that handles any exception raised in the FastAPI application.
    The recommended approach is to register an exception handler for Starlette's HTTPException and
    reuse the default exception handlers from fastapi.exception_handlers.
    References:
    https://fastapi.tiangolo.com/tutorial/handling-errors/#fastapis-httpexception-vs-starlettes-httpexception
    https://fastapi.tiangolo.com/tutorial/handling-errors/#reuse-fastapis-exception-handlers

    Args:
        request: The request object containing information about the incoming request.
        exc: The exception object that was raised.

    Raises:
        HTTPException: With a status code of 500 and a message indicating an internal server error.
    """
    if isinstance(exc, StarletteHTTPException):
        if exc.status_code == 500:
            logging.error(repr(exc))
            raise HTTPException(status_code=exc.status_code, detail="Internal Server Error")  # pragma: no cover
        else:
            return await http_exception_handler(request, exc)
    else:
        logging.error(repr(exc))
        raise HTTPException(status_code=500, detail="Internal Server Error")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8880,
        log_level=logging_level.lower(),
        log_config=LOGGING_CONFIG,
    )
