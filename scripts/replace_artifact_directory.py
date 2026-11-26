"""Publish a staged artifact directory with an atomic directory exchange."""

import ctypes
import errno
import os
from pathlib import Path
import shutil
import sys


def replace_directory(staged: Path, destination: Path) -> None:
    if not destination.exists():
        os.replace(staged, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        exchange = library.renameatx_np
        exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = exchange(-2, os.fsencode(staged), -2, os.fsencode(destination), 2)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        exchange = library.renameat2
        exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = exchange(-100, os.fsencode(staged), -100, os.fsencode(destination), 2)
    else:
        raise OSError(errno.ENOTSUP, "Atomic directory exchange is unavailable on this platform")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))
    # The old directory now occupies the staging path. Non-artifact data was
    # copied into the published directory before exchange.
    shutil.rmtree(staged)


if __name__ == "__main__":
    replace_directory(Path(sys.argv[1]), Path(sys.argv[2]))
