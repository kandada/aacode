# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# File lock utility for cross-process mutual exclusion
# utils/file_lock.py
"""
Reusable file lock using fcntl.flock for cross-process read-modify-write safety.
Works on macOS/Linux. On Windows (no fcntl), falls back to no-op gracefully.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


@contextmanager
def file_lock(filepath):
    """Cross-process exclusive file lock via fcntl.flock.

    Usage:
        with file_lock("/path/to/file.txt"):
            # read, modify, write safely across concurrent processes

    On platforms without fcntl (Windows), the lock is a no-op.

    Args:
        filepath: Path or str pointing to the file to lock.
    """
    filepath = Path(filepath)
    lockfile = filepath.with_suffix(filepath.suffix + ".lock")

    if _HAS_FCNTL:
        with open(lockfile, "a") as lf:
            try:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            try:
                yield
            finally:
                try:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    else:
        yield
