import os

from rustic_ai.api_server.logging.format import (
    HttpAccessJsonFormatter,
    RFC3339JsonFormatter,
)

logging_level = os.environ.get("RUSTIC_LOGGING_LEVEL", "DEBUG")
logging_format = os.environ.get("RUSTIC_LOGGING_FORMAT", "standard")


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {"format": "%(levelname)s:\t %(asctime)s - %(name)s - %(message)s (%(filename)s:%(lineno)d)"},
        "json": {
            "()": RFC3339JsonFormatter,
            "reserved_attrs": ["color_message", "msg", "args"],
            "rename_fields": {"levelname": "level"},
        },
        "access_json": {"()": HttpAccessJsonFormatter, "reserved_attrs": []},
    },
    "handlers": {
        "default": {
            "formatter": logging_format,
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
        "access": {
            "formatter": "access_json" if logging_format == "json" else "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
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
            "handlers": ["access"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": logging_level,
            "handlers": ["default"],
            "propagate": False,
        },
    },
}
