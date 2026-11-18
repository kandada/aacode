# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""TUI entry point: Textual by default, curses as a dependency-free fallback."""

from __future__ import annotations

from typing import Optional


def run_tui(project: Optional[str] = None, session: str = "", model: str = "") -> int:
    try:
        from .textual_app import run_tui as _textual
    except ImportError:
        from .curses_app import run_tui as _fallback
        return _fallback(project=project, session=session, model=model)
    return _textual(project=project, session=session, model=model)
