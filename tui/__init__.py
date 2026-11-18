# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Terminal UI front door for AACode."""

__all__ = ["run_tui"]


def run_tui(*args, **kwargs):
    from .app import run_tui as _run

    return _run(*args, **kwargs)
