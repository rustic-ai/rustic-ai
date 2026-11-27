"""Run a command in a separate POSIX session, preserving its PID for cleanup."""

import os
import sys

if len(sys.argv) < 2:
    sys.exit("Usage: run_in_session.py command [arguments ...]")

os.setsid()
os.execvp(sys.argv[1], sys.argv[1:])
