import os

logging_level = os.environ.get("RUSTIC_LOGGING_LEVEL", "DEBUG")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {"format": "%(levelname)s:\t %(asctime)s - %(name)s - %(message)s (%(filename)s:%(lineno)d)"},
    },
    "handlers": {
        "default": {
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
    },
    "loggers": {
        "": {  # root logger
            "level": logging_level,
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": logging_level,
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": logging_level,
            "handlers": ["default"],
            "propagate": False,
        },
    },
}
