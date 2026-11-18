# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Small .env loader shared by the TUI/CLI paths.

Shell variables win over values from .env files. This mirrors the line CLI's
behaviour while avoiding a hard dependency on python-dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _candidate_files(project: Path | None = None) -> Iterable[Path]:
    roots = [Path.cwd()]
    if project is not None:
        roots.append(Path(project))
    seen: set[Path] = set()
    for root in roots:
        path = root / ".env"
        if path not in seen:
            seen.add(path)
            yield path
    try:
        import platformdirs

        path = Path(platformdirs.user_config_dir("com.aacode", roaming=True)) / ".env"
        if path not in seen:
            yield path
    except Exception:
        return


def load_env_files(
    project: Path | str | None = None,
    override: bool = False,
    skip_keys: tuple[str, ...] | set[str] = (),
) -> None:
    """Load ``.env`` files without clobbering explicit environment variables."""
    for path in _candidate_files(Path(project) if project is not None else None):
        try:
            if not path.is_file():
                continue
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key or key in skip_keys:
                    continue
                if override or key not in os.environ:
                    os.environ[key] = value
        except Exception:
            continue
