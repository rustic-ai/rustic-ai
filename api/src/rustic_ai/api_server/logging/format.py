from datetime import datetime, timezone
import logging
import re

from pythonjsonlogger.json import JsonFormatter


class RusticLogFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(levelname)s:\t %(asctime)s - %(name)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class RFC3339JsonFormatter(JsonFormatter):
    """Standard JSON formatter with RFC 3339 timestamps"""

    def process_log_record(self, log_record):
        """Process the log record and convert timestamp to RFC 3339 format"""
        # Convert timestamp to RFC 3339 format
        if "created" in log_record:
            dt = datetime.fromtimestamp(log_record["created"], tz=timezone.utc)
            log_record["timestamp"] = dt.isoformat()
            # Remove the original timestamp fields to avoid duplication
            log_record.pop("created", None)
            log_record.pop("asctime", None)

        return super().process_log_record(log_record)


class HttpAccessJsonFormatter(RFC3339JsonFormatter):
    """Custom JSON formatter for HTTP access logs with httpRequest structure"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Regex to parse uvicorn access log format: IP:PORT - "METHOD /path HTTP/1.1" STATUS
        self.access_pattern = re.compile(
            r'(?P<remote_ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<remote_port>\d+)\s+-\s+"(?P<method>\w+)\s+(?P<url>\S+)\s+(?P<protocol>HTTP/[\d\.]+)"\s+(?P<status>\d+)'
        )

    def process_log_record(self, log_record):
        """Process the log record and restructure it with httpRequest format"""
        # First, apply RFC 3339 timestamp conversion
        log_record = super().process_log_record(log_record)

        # Get the original message
        message = log_record.get("message", "")

        # Parse the access log message
        match = self.access_pattern.match(message)

        if match:
            groups = match.groupdict()
            http_request = {}

            # Only add fields that are available from uvicorn access logs
            if groups.get("method"):
                http_request["requestMethod"] = groups["method"]

            if groups.get("url"):
                http_request["requestUrl"] = groups["url"]

            if groups.get("status"):
                try:
                    http_request["status"] = int(groups["status"])
                except ValueError:
                    pass

            if groups.get("remote_ip"):
                http_request["remoteIp"] = groups["remote_ip"]

            if groups.get("protocol"):
                http_request["protocol"] = groups["protocol"]

            # Keep timestamp and logger info, replace content with httpRequest
            processed_record = {"timestamp": log_record.get("timestamp"), "httpRequest": http_request}

            return processed_record

        # If parsing fails, return the original log record
        return super().process_log_record(log_record)
