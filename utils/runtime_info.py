# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Runtime identity used to diagnose stale bundled/source copies."""

import platform
import sys
from pathlib import Path
from typing import Dict


def get_runtime_info() -> Dict[str, str]:
    """Return the loaded aacode version/file and interpreter information."""
    import aacode

    package_file = Path(getattr(aacode, "__file__", "")).resolve()
    return {
        "version": str(getattr(aacode, "__version__", "unknown")),
        "file": str(package_file),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
