# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Dependency-free curses fallback TUI for AACode.

The TUI is a thin front door: it spawns ``aacode.tui.worker`` and renders the
worker's JSON event stream. Agent logic, session persistence, compaction, and
usage accounting stay in the core.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from aacode.utils.token_usage import cache_hit_rate, format_cost, format_tokens


def curses_key_up():
    try:
        import curses
        return curses.KEY_UP
    except Exception:
        return -1


def curses_key_down():
    try:
        import curses
        return curses.KEY_DOWN
    except Exception:
        return -2


def curses_key_ppage():
    try:
        import curses
        return curses.KEY_PPAGE
    except Exception:
        return -3


def curses_key_npage():
    try:
        import curses
        return curses.KEY_NPAGE
    except Exception:
        return -4


@dataclass
class Block:
    kind: str
    text: str = ""
    tool: str = ""
    call_id: str = ""
    status: str = ""
    duration_ms: int = 0
    collapsed: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)


class Worker:
    """Run one task in a subprocess and expose its JSON events."""

    def __init__(self, project: Path, workdir: Path):
        self.project = project
        self.workdir = workdir
        self.proc: Optional[subprocess.Popen] = None
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, task: str, session: str = "", model: str = "", max_iterations: int = 0, compact: bool = False) -> None:
        if self.running():
            return
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["AACODE_JSON_EVENTS"] = "1"
        env.setdefault("AACODE_USAGE_QUIET", "1")
        # The worker is launched with the target project as cwd, which may be
        # outside this checkout. Keep the package importable when running from
        # a source tree without an installed console script.
        _package_root = Path(__file__).resolve().parents[2]
        _old_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(_package_root) + (os.pathsep + _old_path if _old_path else "")
        cmd = [
            sys.executable, "-m", "aacode.tui.worker",
            "--project", str(self.project),
            "--workdir", str(self.workdir),
            "--task", task,
        ]
        if compact:
            cmd.append("--compact")
        if session:
            cmd += ["--session", session]
        if model:
            cmd += ["--model", model]
        if max_iterations > 0:
            cmd += ["--max-iterations", str(max_iterations)]
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(self.project),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.events.put({"type": "worker_error", "error": str(exc)})
            return
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        self.events.put(payload)
                        continue
                except Exception:
                    pass
            # Human-oriented output is intentionally ignored by the TUI.
        self.events.put({"type": "worker_exit"})

    def cancel(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass


class TuiApp:
    def __init__(self, project: Path, session: str = "", model: str = ""):
        self.project = project
        self.workdir = project
        self.session_id = session
        self.model = model
        self.worker = Worker(project, self.workdir)
        self.blocks: List[Block] = []
        self.current_assistant: Optional[Block] = None
        self.current_thinking: Optional[Block] = None
        self.tool_blocks: Dict[str, Block] = {}
        self.usage: Dict[str, Any] = {}
        self.context_tokens = 0
        self.context_window = 0
        self.cache_rate: Optional[float] = None
        self.cost: Optional[float] = None
        self.currency: str = ""
        self.status = "idle"
        self.input = ""
        self.history: List[str] = []
        self.history_index = -1
        self.scroll = 0
        self.show_tools = True
        self.show_thinking = True
        self.quit = False
        self.spinner = 0
        self.last_error = ""
        self.panel: Optional[Dict[str, Any]] = None
        self._add_system(
            "AACode TUI — type a task and press Enter. /help for commands, Esc cancels, Ctrl+C exits."
        )

    # ── blocks ────────────────────────────────────────────────────
    def _add_system(self, text: str) -> None:
        self.blocks.append(Block(kind="system", text=text))

    def _add_user(self, text: str) -> None:
        self.blocks.append(Block(kind="user", text=text))

    def _add_error(self, text: str) -> None:
        self.blocks.append(Block(kind="error", text=text))

    def _ensure_assistant(self) -> Block:
        if self.current_assistant is None:
            self.current_assistant = Block(kind="assistant", text="")
            self.blocks.append(self.current_assistant)
        return self.current_assistant

    def _ensure_thinking(self) -> Block:
        if self.current_thinking is None:
            self.current_thinking = Block(kind="thinking", text="")
            self.blocks.append(self.current_thinking)
        return self.current_thinking

    def _handle_event(self, event: Dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "worker_ready":
            self.session_id = event.get("session_id") or self.session_id
            if event.get("model"):
                self.model = event.get("model")
            self.status = "running"
        elif kind == "text_delta":
            text = event.get("text", "")
            if not text:
                return
            if event.get("kind") == "thinking":
                if self.show_thinking:
                    self._ensure_thinking().text += text
            else:
                self.current_thinking = None
                self._ensure_assistant().text += text
        elif kind == "tool_progress":
            name = event.get("name") or "tool"
            call_id = event.get("call_id") or f"progress_{len(self.tool_blocks)}"
            if call_id not in self.tool_blocks:
                block = Block(kind="tool", tool=name, call_id=call_id, status="building")
                self.tool_blocks[call_id] = block
                self.blocks.append(block)
        elif kind == "tool_status":
            call_id = event.get("call_id", "")
            block = self.tool_blocks.get(call_id)
            if block is None:
                block = Block(kind="tool", tool=event.get("tool", "tool"), call_id=call_id)
                self.tool_blocks[call_id] = block
                self.blocks.append(block)
            block.status = event.get("status", "")
            block.duration_ms = int(event.get("duration_ms") or 0)
        elif kind == "tool_result":
            call_id = event.get("call_id", "")
            block = self.tool_blocks.get(call_id)
            if block is None:
                block = Block(kind="tool", tool=event.get("tool", "tool"), call_id=call_id)
                self.tool_blocks[call_id] = block
                self.blocks.append(block)
            block.status = event.get("status", block.status or "success")
            block.duration_ms = int(event.get("duration_ms") or block.duration_ms)
            block.text = event.get("content", "")
        elif kind == "usage":
            self.usage = event.get("usage") or {}
            self.context_tokens = int(event.get("context_tokens") or self.context_tokens)
            self.context_window = int(event.get("context_window") or self.context_window)
            self.cache_rate = event.get("cache_hit_rate")
            self.cost = event.get("cost")
            self.currency = event.get("currency") or self.currency
        elif kind == "compaction":
            self._add_system(
                f"📦 Compaction: {event.get('pruned', 0)} tool results pruned, "
                f"summary={'yes' if event.get('summary') else 'no'}, "
                f"context ~{format_tokens(int(event.get('tokens') or 0))} tokens"
            )
        elif kind == "repeat_reminder":
            self._add_system(event.get("text", "Repeated tool call detected."))
        elif kind == "tool_spill":
            self._add_system(
                f"💾 Spilled {event.get('tool')} output ({event.get('original_chars', 0)} chars) "
                f"to {event.get('path')}"
            )
        elif kind == "task_start":
            self.status = "running"
            if event.get("session_id"):
                self.session_id = event.get("session_id")
        elif kind == "task_end":
            self.status = event.get("status", "idle")
            self._add_system(f"Task {self.status}.")
        elif kind == "compact_done":
            self.status = "idle"
            result = event.get("result") or {}
            if result.get("status") == "compacted":
                self._add_system(
                    f"📦 Compacted: cutoff {result.get('cutoff_before')} → "
                    f"{result.get('cutoff_after')} · ~{format_tokens(int(result.get('tokens') or 0))} tokens"
                    + (" · summary" if result.get("summary") else "")
                    + (f" · {result.get('pruned')} tool results pruned" if result.get("pruned") else "")
                )
            else:
                self._add_system(f"Compaction: {result.get('status', 'noop')}")
        elif kind == "worker_done":
            self.status = "idle"
            result = event.get("result") or {}
            if result.get("status") and result.get("status") != "completed":
                self._add_system(f"Task ended: {result.get('status')}")
            usage = event.get("usage") or {}
            if usage:
                self.usage = usage
        elif kind == "worker_error":
            self.status = "error"
            self.last_error = event.get("error", "unknown error")
            self._add_error(self.last_error)
        elif kind == "worker_cancelled":
            self.status = "idle"
            self._add_system("Task cancelled.")
        elif kind == "worker_exit":
            if self.status == "running":
                self.status = "idle"
            self.current_assistant = None
            self.current_thinking = None
        elif kind == "session_switched":
            if event.get("ok"):
                self.session_id = event.get("session_id") or self.session_id

    # ── panels ───────────────────────────────────────────────────
    def _open_panel(self, kind: str, title: str, items: List[Dict[str, Any]], data: Optional[Dict[str, Any]] = None) -> None:
        self.panel = {
            "kind": kind,
            "title": title,
            "items": items,
            "selected": 0,
            "query": "",
            "data": data or {},
        }
        self.input = ""

    def _close_panel(self) -> None:
        self.panel = None

    def _filtered_panel_items(self) -> List[Dict[str, Any]]:
        if not self.panel:
            return []
        query = (self.panel.get("query") or "").lower()
        items = self.panel.get("items") or []
        if not query:
            return items
        return [
            item for item in items
            if query in (item.get("label", "") + " " + item.get("desc", "")).lower()
        ]

    def _open_sessions_panel(self) -> None:
        index = self.project / ".aacode" / "sessions" / "sessions_index.json"
        items: List[Dict[str, Any]] = []
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            rows = sorted(
                data.items(),
                key=lambda kv: str((kv[1] or {}).get("last_activity") or ""),
                reverse=True,
            )
            for sid, info in rows[:50]:
                info = info or {}
                title = str(info.get("title") or "")[:60]
                when = str(info.get("last_activity") or "")[:19]
                mark = "● " if sid == self.session_id else "  "
                items.append({
                    "id": sid,
                    "label": f"{mark}{title or sid}",
                    "desc": f"{sid}  ·  {when}",
                    "action": "resume",
                })
        except Exception as exc:
            items.append({"id": "", "label": f"No session index: {exc}", "desc": "", "action": "none"})
        self._open_panel("sessions", "Sessions  ·  Enter to select for the next task", items)

    def _open_models_panel(self) -> None:
        items: List[Dict[str, Any]] = []
        try:
            from aacode.config import settings
            models = settings.model.models or {}
            for key, entry in models.items():
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or key)
                profile = settings.get_model_profile(name)
                window = profile.get("context_window") or settings.context.max_context_length
                output = profile.get("max_output_tokens") or ""
                mark = "● " if name == self.model else "  "
                items.append({
                    "id": name,
                    "label": f"{mark}{name}",
                    "desc": f"{key}  ·  window {window}  ·  output {output or 'default'}",
                    "action": "model",
                })
        except Exception as exc:
            items.append({"id": "", "label": f"Model list unavailable: {exc}", "desc": "", "action": "none"})
        if self.model and not any(item.get("id") == self.model for item in items):
            items.insert(0, {
                "id": self.model,
                "label": f"● {self.model}",
                "desc": "current selection",
                "action": "model",
            })
        self._open_panel("models", "Models  ·  Enter to select for the next task", items)

    def _open_settings_panel(self) -> None:
        try:
            from aacode.config import settings
            ctx = settings.context
            rows = [
                ("Context window", str(settings.context.max_context_length)),
                ("Window ratio", str(ctx.window_ratio)),
                ("Headroom tokens", str(ctx.headroom_tokens)),
                ("Retain ratio", str(ctx.retain_ratio)),
                ("Retain tokens", str(ctx.retain_tokens)),
                ("Cost ceiling", str(ctx.cost_ceiling_tokens)),
                ("Summary mode", str(ctx.summary_mode)),
                ("Summary min shadow", str(ctx.summary_min_shadow_tokens)),
                ("Prune enabled", str(ctx.prune_enabled)),
                ("Prune threshold/head/tail", f"{ctx.prune_threshold_chars}/{ctx.prune_head_chars}/{ctx.prune_tail_chars}"),
                ("Tool profile", str(settings.tools.tool_profile)),
                ("Max iterations", str(settings.agent.max_react_iterations)),
                ("Summary model", str(ctx.summary_model or "(main route)")),
                ("Show tool cards", "on" if self.show_tools else "off"),
                ("Show thinking", "on" if self.show_thinking else "off"),
            ]
        except Exception as exc:
            rows = [("Settings unavailable", str(exc))]
        items = [
            {"id": key, "label": key, "desc": value, "action": "setting"}
            for key, value in rows
        ]
        path = ""
        try:
            from aacode.config import settings
            path = str(getattr(settings, "config_path", "") or "")
        except Exception:
            pass
        self._open_panel(
            "settings",
            "Settings  ·  Enter toggles display rows · e opens the YAML in $EDITOR",
            items,
            {"config_path": path},
        )

    def _edit_config(self) -> None:
        """Open the real config YAML in $EDITOR, then reload settings."""
        import curses
        try:
            from aacode.config import settings
            path = getattr(settings, "config_path", None)
        except Exception as exc:
            self._add_system(f"Config editor unavailable: {exc}")
            return
        if not path:
            self._add_system("No config file path is available.")
            return
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        cmd = shlex.split(editor) + [str(path)]
        try:
            curses.def_prog_mode()
            curses.endwin()
        except Exception:
            pass
        try:
            subprocess.run(cmd, check=False)
        except Exception as exc:
            self._add_system(f"Could not open editor {editor}: {exc}")
        finally:
            try:
                curses.reset_prog_mode()
                stdscr = curses.initscr()
                stdscr.clear()
                stdscr.refresh()
            except Exception:
                pass
        try:
            settings.load_config()
        except Exception as exc:
            self._add_system(f"Config saved, but reload failed: {exc}")
        self._open_settings_panel()
        self._add_system(f"Config reloaded from {path}.")

    def _open_help_panel(self) -> None:
        lines = [
            ("Commands", "/help /usage /sessions /resume /model /settings /compact /tools /thinking /clear /cancel /exit"),
            ("Task", "Type a task and press Enter. Esc cancels a running task."),
            ("Sessions", "/sessions or /resume opens a searchable session list."),
            ("Models", "/model opens the model selector; /model <name> sets it directly."),
            ("Usage", "/usage opens context, cache, token, and cost details."),
            ("Tool cards", "Ctrl+O toggles tool output; Enter on a card? (Ctrl+O global)"),
            ("Thinking", "Ctrl+T toggles thinking blocks."),
            ("Scroll", "PgUp / PgDn scrolls the transcript; Up/Down edits history when idle."),
            ("Cancel/Exit", "Esc cancels; Ctrl+C exits."),
            ("Config", "/settings then press e to edit aacode_config.yaml in $EDITOR."),
        ]
        items = [{"id": k, "label": k, "desc": v, "action": "help"} for k, v in lines]
        self._open_panel("help", "Help  ·  Esc / Enter to close", items)

    def _open_usage_panel(self) -> None:
        items = [
            {"id": "summary", "label": "Summary", "desc": self._usage_text(), "action": "usage"},
            {"id": "context", "label": "Context", "desc": f"{format_tokens(self.context_tokens)} / {format_tokens(self.context_window)}", "action": "usage"},
            {"id": "cache", "label": "Cache hit", "desc": f"{self.cache_rate:.1%}" if self.cache_rate is not None else "unknown", "action": "usage"},
            {"id": "cost", "label": "Estimated cost", "desc": format_cost(self.cost, self.currency), "action": "usage"},
        ]
        self._open_panel("usage", "Usage  ·  Esc / Enter to close", items)

    def _handle_panel_key(self, key: Any) -> None:
        if not self.panel:
            return
        if key == "\x03":
            self.quit = True
            return
        if key == "\x1b" or key in ("q", "Q"):
            self._close_panel()
            return
        if self.panel.get("kind") == "settings" and key in ("e", "E"):
            self._edit_config()
            return
        if key in ("\n", "\r"):
            items = self._filtered_panel_items()
            if not items:
                self._close_panel()
                return
            selected = items[min(self.panel.get("selected", 0), len(items) - 1)]
            action = selected.get("action")
            if action == "resume" and selected.get("id"):
                self.session_id = selected["id"]
                self._add_system(f"Next task will resume session {self.session_id}.")
                self._close_panel()
            elif action == "model" and selected.get("id"):
                self.model = selected["id"]
                self._add_system(f"Next task will use model {self.model}.")
                self._close_panel()
            elif action == "setting":
                ident = selected.get("id")
                if ident == "Show tool cards":
                    self.show_tools = not self.show_tools
                elif ident == "Show thinking":
                    self.show_thinking = not self.show_thinking
                else:
                    path = (self.panel.get("data") or {}).get("config_path") or "aacode_config.yaml"
                    self._add_system(f"Edit {path} to change {ident}.")
                self._open_settings_panel()
            else:
                self._close_panel()
            return
        if key == curses_key_up():
            self.panel["selected"] = max(0, self.panel.get("selected", 0) - 1)
            return
        if key == curses_key_down():
            items = self._filtered_panel_items()
            self.panel["selected"] = min(max(0, len(items) - 1), self.panel.get("selected", 0) + 1)
            return
        if key == curses_key_ppage():
            self.panel["selected"] = max(0, self.panel.get("selected", 0) - 10)
            return
        if key == curses_key_npage():
            items = self._filtered_panel_items()
            self.panel["selected"] = min(max(0, len(items) - 1), self.panel.get("selected", 0) + 10)
            return
        if key in ("\x7f", "\b"):
            self.panel["query"] = (self.panel.get("query") or "")[:-1]
            self.panel["selected"] = 0
            return
        if isinstance(key, str) and key.isprintable():
            if self.panel.get("kind") in ("sessions", "models"):
                self.panel["query"] = (self.panel.get("query") or "") + key
                self.panel["selected"] = 0

    # ── commands ──────────────────────────────────────────────────
    def _run_command(self, text: str) -> None:
        parts = shlex.split(text)
        if not parts:
            return
        cmd = parts[0].lower()
        if cmd in ("/help", "/h", "/?"):
            self._open_help_panel()
        elif cmd in ("/usage", "/cost", "/tokens"):
            self._open_usage_panel()
        elif cmd in ("/sessions", "/session"):
            self._open_sessions_panel()
        elif cmd == "/resume":
            if len(parts) > 1:
                self.session_id = parts[1]
                self._add_system(f"Next task will resume session {self.session_id}.")
            else:
                self._open_sessions_panel()
        elif cmd == "/model":
            if len(parts) > 1:
                self.model = parts[1]
                self._add_system(f"Next task will use model {self.model}.")
            else:
                self._open_models_panel()
        elif cmd in ("/settings", "/config"):
            self._open_settings_panel()
        elif cmd == "/tools":
            self.show_tools = not self.show_tools
            self._add_system(f"Tool cards {'shown' if self.show_tools else 'hidden'}.")
        elif cmd == "/thinking":
            self.show_thinking = not self.show_thinking
            self._add_system(f"Thinking blocks {'shown' if self.show_thinking else 'hidden'}.")
        elif cmd == "/clear":
            self.blocks = []
            self.current_assistant = None
            self.current_thinking = None
            self.tool_blocks = {}
        elif cmd == "/compact":
            if self.worker.running():
                self._add_system("A task is running; cancel it before compacting.")
            else:
                self.status = "running"
                self._add_system("📦 Compacting the current session…")
                self.worker.start("", self.session_id, self.model, compact=True)
        elif cmd == "/cancel":
            self._cancel()
        elif cmd in ("/exit", "/quit", "/q"):
            self.quit = True
        else:
            self._add_system(f"Unknown command: {cmd}. /help for commands.")

    def _usage_text(self) -> str:
        rate = cache_hit_rate(self.usage) if self.usage else self.cache_rate
        cost = self.cost
        parts = [
            f"calls {self.usage.get('calls', 0)}",
            f"prompt {format_tokens(int(self.usage.get('prompt_total', 0) or 0))}",
            f"uncached {format_tokens(int(self.usage.get('uncached_input', 0) or 0))}",
            f"cache read {format_tokens(int(self.usage.get('cache_read', 0) or 0))}",
            f"output {format_tokens(int(self.usage.get('output', 0) or 0))}",
            f"cache hit {rate:.1%}" if rate is not None else "cache hit unknown",
            f"cost {format_cost(cost, self.currency)}",
        ]
        return "Usage: " + " · ".join(parts)

    def _sessions_text(self) -> str:
        index = self.project / ".aacode" / "sessions" / "sessions_index.json"
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except Exception:
            return "No session index found."
        rows = []
        for sid, info in list(data.items())[:12]:
            title = str(info.get("title") or "")[:50]
            rows.append(f"{sid}  {title}")
        return "Sessions:\n" + "\n".join(rows) if rows else "No sessions."

    # ── input/worker ──────────────────────────────────────────────
    def _send(self) -> None:
        task = self.input.strip()
        if not task:
            return
        self.input = ""
        if task.startswith("/"):
            self._run_command(task)
            return
        if self.worker.running():
            self._add_system("A task is already running. Press Esc to cancel it first.")
            return
        self.history.append(task)
        self.history_index = -1
        self._add_user(task)
        self.current_assistant = None
        self.current_thinking = None
        self.status = "running"
        self.scroll = 0
        self.worker.start(task, self.session_id, self.model)

    def _cancel(self) -> None:
        if self.worker.running():
            self.worker.cancel()
            self.status = "idle"
            self._add_system("Cancelling task…")

    # ── rendering ─────────────────────────────────────────────────
    def _wrap(self, text: str, width: int) -> List[str]:
        if not text:
            return [""]
        lines: List[str] = []
        for raw in text.splitlines() or [""]:
            if not raw:
                lines.append("")
                continue
            lines.extend(textwrap.wrap(raw, width=max(10, width)) or [""])
        return lines

    def _decorate_text(self, text: str, width: int) -> List[tuple]:
        """Lightweight markdown styling for the terminal transcript."""
        rendered: List[tuple] = []
        in_code = False
        for line in self._wrap(text, width):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                rendered.append((line, "code-label"))
                continue
            if in_code:
                rendered.append((line, "code"))
            elif stripped.startswith("#"):
                rendered.append((line, "heading"))
            elif re.match(r"^\s*[-*+]\s+", line):
                rendered.append((line, "bullet"))
            elif stripped.startswith(">"):
                rendered.append((line, "quote"))
            else:
                rendered.append((line, "assistant"))
        return rendered

    def _render_blocks(self, width: int) -> List[tuple]:
        rendered: List[tuple] = []
        for block in self.blocks:
            if block.kind == "user":
                for line in self._wrap(block.text, width - 2):
                    rendered.append(("> " + line if line else ">", "user"))
            elif block.kind == "assistant":
                rendered.extend(self._decorate_text(block.text, width))
            elif block.kind == "thinking":
                if not self.show_thinking:
                    continue
                lines = self._wrap(block.text, width - 2)
                if block.collapsed and len(lines) > 3:
                    lines = lines[:3] + ["… (Ctrl+T to expand thinking)"]
                for line in lines:
                    rendered.append(("  " + line, "thinking"))
            elif block.kind == "tool":
                if not self.show_tools:
                    continue
                duration = f" {block.duration_ms / 1000:.1f}s" if block.duration_ms else ""
                status = block.status or "running"
                rendered.append((f"🔧 {block.tool} [{status}]{duration}", "tool"))
                lines = self._wrap(block.text, width - 4)
                if block.collapsed and len(lines) > 4:
                    lines = lines[:4] + ["… (Ctrl+O to expand tool output)"]
                for line in lines:
                    rendered.append(("  " + line, "tool-body"))
            elif block.kind == "system":
                for line in self._wrap(block.text, width - 2):
                    rendered.append((line, "system"))
            elif block.kind == "error":
                for line in self._wrap(block.text, width - 2):
                    rendered.append((line, "error"))
        return rendered

    def _status_line(self) -> str:
        parts = []
        if self.model:
            parts.append(self.model)
        if self.session_id:
            parts.append(self.session_id)
        if self.context_window:
            pct = min(100, round(self.context_tokens / self.context_window * 100))
            parts.append(f"ctx {format_tokens(self.context_tokens)} ({pct}%)")
        elif self.context_tokens:
            parts.append(f"ctx {format_tokens(self.context_tokens)}")
        if self.cache_rate is not None:
            parts.append(f"cache {self.cache_rate:.0%}")
        if self.usage:
            parts.append(f"↑{format_tokens(int(self.usage.get('prompt_total', 0) or 0))} "
                         f"↓{format_tokens(int(self.usage.get('output', 0) or 0))}")
            if self.cost is not None:
                parts.append(format_cost(self.cost, self.currency))
        parts.append(self.status)
        return " · ".join(parts)

    def _draw_panel(self, stdscr, top: int, bottom: int, width: int) -> None:
        import curses
        if not self.panel or bottom <= top:
            return
        title = self.panel.get("title", "")
        query = self.panel.get("query") or ""
        kind = self.panel.get("kind")
        if kind in ("sessions", "models"):
            header = f"{title}   filter: {query or '—'}"
        else:
            header = title
        try:
            stdscr.addnstr(top, 0, " " * max(0, width - 1), width - 1, curses.color_pair(8))
            stdscr.addnstr(top, 0, header, width - 1, curses.color_pair(8) | curses.A_BOLD)
        except curses.error:
            pass
        items = self._filtered_panel_items()
        selected = min(self.panel.get("selected", 0), max(0, len(items) - 1))
        max_rows = max(0, bottom - top - 2)
        start = max(0, selected - max_rows // 2)
        start = min(start, max(0, len(items) - max_rows))
        for row, item in enumerate(items[start:start + max_rows]):
            y = top + 1 + row
            index = start + row
            label = str(item.get("label", ""))
            desc = str(item.get("desc", ""))
            line = f"{label}  —  {desc}" if desc else label
            attr = curses.color_pair(3) | curses.A_BOLD if index == selected else curses.A_NORMAL
            try:
                if index == selected:
                    stdscr.addnstr(y, 0, " " * max(0, width - 1), width - 1, attr)
                stdscr.addnstr(y, 1, line, max(0, width - 2), attr)
            except curses.error:
                pass
        hint = "↑↓ select · Enter confirm · Esc close · type to filter" if kind in ("sessions", "models") else "Enter / Esc to close"
        try:
            stdscr.addnstr(bottom - 1, 1, hint, max(0, width - 2), curses.color_pair(7) | curses.A_DIM)
        except curses.error:
            pass

    def draw(self, stdscr) -> None:
        import curses

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 8 or w < 30:
            stdscr.addnstr(0, 0, "Terminal too small (need ≥ 30x8)", max(0, w - 1))
            stdscr.refresh()
            return

        header = f"AACode  ·  {self.project.name}  ·  {self.project}"
        stdscr.addnstr(0, 0, header, w - 1, curses.A_BOLD if hasattr(curses, "A_BOLD") else 0)

        input_height = 3
        status_y = h - input_height - 1
        transcript_top = 1
        transcript_height = max(1, status_y - transcript_top)

        rendered = self._render_blocks(max(10, w - 2))
        total = len(rendered)
        visible = transcript_height
        max_scroll = max(0, total - visible)
        self.scroll = max(0, min(self.scroll, max_scroll))
        start = max(0, total - visible - self.scroll)
        start = min(start, max(0, total - visible))
        for row, (text, kind) in enumerate(rendered[start:start + visible]):
            attr = curses.A_NORMAL
            if kind == "user":
                attr = curses.color_pair(2) | curses.A_BOLD
            elif kind == "thinking":
                attr = curses.color_pair(7) | curses.A_DIM
            elif kind == "tool":
                attr = curses.color_pair(4) | curses.A_BOLD
            elif kind == "tool-body":
                attr = curses.color_pair(4)
            elif kind == "system":
                attr = curses.color_pair(5)
            elif kind == "error":
                attr = curses.color_pair(6) | curses.A_BOLD
            elif kind == "heading":
                attr = curses.color_pair(10) | curses.A_BOLD
            elif kind == "code-label":
                attr = curses.color_pair(9) | curses.A_DIM
            elif kind == "code":
                attr = curses.color_pair(9)
            elif kind == "bullet":
                attr = curses.color_pair(11)
            elif kind == "quote":
                attr = curses.color_pair(12) | curses.A_DIM
            try:
                stdscr.addnstr(transcript_top + row, 0, text, w - 1, attr)
            except curses.error:
                pass

        if self.panel:
            self._draw_panel(stdscr, transcript_top, status_y, w)

        stdscr.addnstr(status_y, 0, " " * (w - 1), w - 1, curses.color_pair(8))
        stdscr.addnstr(status_y, 0, self._status_line(), w - 1, curses.color_pair(8))

        if self.panel and self.panel.get("kind") in ("sessions", "models"):
            prompt = "filter: " + (self.panel.get("query") or "")
        elif self.panel:
            prompt = "panel: Enter/Esc"
        else:
            prompt = "> " + self.input
        wrapped = self._wrap(prompt, w - 2)
        if len(wrapped) > input_height:
            wrapped = wrapped[-input_height:]
        for idx, line in enumerate(wrapped):
            y = status_y + 1 + idx
            if y >= h:
                break
            try:
                stdscr.addnstr(y, 0, line, w - 1, curses.A_BOLD if idx == 0 else curses.A_NORMAL)
            except curses.error:
                pass
        try:
            if self.panel and self.panel.get("kind") in ("sessions", "models"):
                cursor_x = min(w - 2, 8 + len(self.panel.get("query") or ""))
            elif self.panel:
                cursor_x = min(w - 2, 12)
            else:
                cursor_x = min(w - 2, 2 + len(self.input.splitlines()[-1] if self.input else ""))
            stdscr.move(h - 1, cursor_x)
        except curses.error:
            pass
        stdscr.refresh()

    def run(self, stdscr):
        import curses

        try:
            curses.curs_set(1)
        except Exception:
            pass
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, -1, -1)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_GREEN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
            curses.init_pair(5, curses.COLOR_MAGENTA, -1)
            curses.init_pair(6, curses.COLOR_RED, -1)
            curses.init_pair(7, curses.COLOR_WHITE, -1)
            curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(9, curses.COLOR_GREEN, -1)
            curses.init_pair(10, curses.COLOR_CYAN, -1)
            curses.init_pair(11, curses.COLOR_YELLOW, -1)
            curses.init_pair(12, curses.COLOR_MAGENTA, -1)
        except Exception:
            pass
        stdscr.keypad(True)
        stdscr.nodelay(True)
        curses.cbreak()
        curses.noecho()

        while not self.quit:
            # Drain worker events.
            while True:
                try:
                    event = self.worker.events.get_nowait()
                except queue.Empty:
                    break
                self._handle_event(event)
                if self.scroll == 0:
                    pass

            # Input.
            try:
                key = stdscr.get_wch()
            except curses.error:
                key = None
            if key is not None and self.panel is not None:
                self._handle_panel_key(key)
                key = None
            if key is not None:
                if key == "\x03":  # Ctrl+C
                    self._cancel()
                    self.quit = True
                    break
                elif key == "\x1b":  # Esc
                    if self.worker.running():
                        self._cancel()
                    else:
                        self.input = ""
                elif key in ("\n", "\r"):
                    self._send()
                elif key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                    self.input = self.input[:-1]
                elif key == "\x0f":  # Ctrl+O
                    self.show_tools = not self.show_tools
                    if self.show_tools:
                        for block in self.tool_blocks.values():
                            block.collapsed = not block.collapsed
                elif key == "\x14":  # Ctrl+T
                    self.show_thinking = not self.show_thinking
                elif key == curses.KEY_UP:
                    if self.input:
                        if self.history:
                            self.history_index = min(self.history_index + 1, len(self.history) - 1)
                            self.input = self.history[len(self.history) - 1 - self.history_index]
                    else:
                        self.scroll += 3
                elif key == curses.KEY_DOWN:
                    if self.input:
                        self.history_index = max(-1, self.history_index - 1)
                        self.input = "" if self.history_index < 0 else self.history[len(self.history) - 1 - self.history_index]
                    else:
                        self.scroll = max(0, self.scroll - 3)
                elif key == curses.KEY_PPAGE:
                    self.scroll += 15
                elif key == curses.KEY_NPAGE:
                    self.scroll = max(0, self.scroll - 15)
                elif isinstance(key, str) and key.isprintable():
                    self.input += key

            self.spinner += 1
            self.draw(stdscr)
            time.sleep(0.05)

        self.worker.cancel()
        return 0


def run_tui(project: Optional[str] = None, session: str = "", model: str = "") -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("aacode tui requires an interactive terminal (TTY).", file=sys.stderr)
        return 2
    try:
        import curses
    except Exception as exc:
        print(f"curses is unavailable: {exc}", file=sys.stderr)
        return 2
    project_path = Path(project or os.getcwd()).absolute()
    app = TuiApp(project_path, session=session, model=model)
    try:
        return curses.wrapper(app.run) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"AACode TUI could not start: {exc}", file=sys.stderr)
        return 2
    finally:
        app.worker.cancel()
