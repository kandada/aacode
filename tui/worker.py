# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Headless worker for the TUI.

The worker owns the real agent; the TUI only parses one JSON event per line.
This keeps the terminal screen free of the agent's human-oriented prints and
avoids a second agent implementation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path


def _emit(payload):
    try:
        print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    except Exception:
        pass


async def _run(args) -> int:
    project = Path(args.project or args.workdir or os.getcwd()).absolute()
    workdir = Path(args.workdir or project).absolute()
    try:
        from aacode.utils.env_loader import load_env_files
        from aacode.config import settings as _settings
        skip = {"LLM_API_KEY", "LLM_API_URL", "LLM_MODEL_NAME", "LLM_GATEWAY"} if _settings.model.api_key else set()
        load_env_files(project, skip_keys=skip)
    except Exception:
        pass
    os.environ["AACODE_JSON_EVENTS"] = "1"
    os.environ.setdefault("AACODE_USAGE_QUIET", "1")
    # The TUI needs an immediate first token; project scanning is optional and
    # can be performed by the agent with tools once the conversation starts.
    os.environ.setdefault("AACODE_SKIP_PROJECT_ANALYSIS", "1")
    if args.model:
        os.environ["LLM_MODEL_NAME"] = args.model

    from aacode.main import AICoder

    try:
        coder = AICoder(
            project_path=str(workdir),
            target_project=str(project),
        )
        if args.session:
            ok = await coder.main_agent.session_manager.switch_session(args.session)
            _emit({"type": "session_switched", "session_id": args.session, "ok": bool(ok)})
        _emit({
            "type": "worker_ready",
            "project": str(project),
            "session_id": coder.main_agent.session_manager.current_session_id,
            "model": coder.main_agent.model_config.get("name"),
        })
        if args.compact:
            compact_result = await coder.main_agent.compact_context()
            _emit({
                "type": "compact_done",
                "result": compact_result,
                "session_id": coder.main_agent.session_manager.current_session_id,
                "usage": coder.main_agent.session_manager.get_usage_summary(),
            })
            return 0
        result = await coder.run(
            args.task,
            max_iterations=args.max_iterations,
            event_callback=_emit,
        )
        _emit({
            "type": "worker_done",
            "result": result,
            "session_id": coder.main_agent.session_manager.current_session_id,
            "usage": coder.main_agent.session_manager.get_usage_summary(),
        })
        return 0
    except asyncio.CancelledError:
        _emit({"type": "worker_cancelled"})
        return 130
    except Exception as exc:
        _emit({"type": "worker_error", "error": str(exc), "traceback": traceback.format_exc()[-4000:]})
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="AACode TUI worker")
    parser.add_argument("--project", default="")
    parser.add_argument("--workdir", default="")
    parser.add_argument("--session", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.compact and not args.task:
        parser.error("--task is required unless --compact is used")
    try:
        from aacode.config import settings
        if args.max_iterations <= 0:
            args.max_iterations = int(getattr(settings.agent, "max_react_iterations", 300) or 300)
    except Exception:
        if args.max_iterations <= 0:
            args.max_iterations = 300
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
