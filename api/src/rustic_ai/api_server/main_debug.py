import ptvsd
import uvicorn

from rustic_ai.api_server.logging import LOGGING_CONFIG

from .main import app, logging_level

if __name__ == "__main__":
    ptvsd.enable_attach(address=("0.0.0.0", 5678))
    ptvsd.wait_for_attach()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8880,
        log_level=logging_level.lower(),
        log_config=LOGGING_CONFIG,
    )
