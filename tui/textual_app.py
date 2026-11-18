# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""OpenCode-inspired Textual TUI for AACode.

The TUI is intentionally a thin front door: it owns rendering and input, while
``aacode.tui.worker`` runs the real agent in a subprocess and streams newline
delimited JSON events back. This keeps compaction, sessions, and usage
accounting in one place.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import time
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Input, Markdown, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from aacode import __version__
from aacode.utils.env_loader import load_env_files
from aacode.utils.token_usage import cache_hit_rate, format_cost, format_tokens

from .curses_app import Worker

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# One-cell block motion inspired by OpenCode's mini TUI. Block frames are
# deliberately used instead of octant glyphs so the animation works in the
# broadest range of terminals.
WORK_FRAMES = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"
TOOL_FRAMES = "◐◓◑◒"
WORK_COLORS = ("#d29922", "#e3b341", "#f0b429", "#e3b341")

SLASH_COMMANDS = [
    ("/help", "Keyboard shortcuts and commands"),
    ("/model", "Choose the model for the next task"),
    ("/models", "Alias for /model"),
    ("/settings", "Inspect settings; e edits the YAML in $EDITOR"),
    ("/config", "Alias for /settings"),
    ("/reload", "Reload the configuration file"),
    ("/sessions", "Resume a previous session"),
    ("/resume", "Resume a session by id"),
    ("/usage", "Tokens, cache hit rate, context, and cost"),
    ("/compact", "Compact the current session"),
    ("/copy", "Copy the last assistant answer"),
    ("/tools", "Show or hide tool cards"),
    ("/thinking", "Show or hide reasoning blocks"),
    ("/clear", "Clear the transcript"),
    ("/cancel", "Cancel the running task"),
    ("/setup", "Show LLM configuration help"),
    ("/exit", "Exit AACode"),
]


def _plain(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _short(value: str, limit: int = 60) -> str:
    value = (value or "").replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _fade_in(widget: Any, duration: float = 0.22) -> None:
    """Small entry animation; ignored by terminals with animations disabled."""
    try:
        widget.styles.opacity = 0
        widget.styles.animate("opacity", 1, duration=duration)
    except Exception:
        pass


def _shimmer_text(
    text: str,
    phase: float,
    base: str = "#d29922",
    highlight: str = "#fff2b0",
    width: int = 4,
) -> Text:
    """Return text with a moving highlight band (OpenCode-style shimmer)."""
    if not text:
        return Text("")
    length = len(text)
    front = (phase % 1.0) * (length + width * 2) - width
    rendered = Text()
    for index, char in enumerate(text):
        distance = abs(index - front)
        if distance <= 1:
            style = f"bold {highlight}"
        elif distance <= width:
            style = highlight
        elif distance <= width + 3:
            style = "#e3b341" if base == "#d29922" else base
        else:
            style = base
        rendered.append(char, style=style)
    return rendered


class Composer(TextArea):
    """Composer with Enter-to-send and Shift+Enter/Ctrl+J newline."""

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        try:
            self.app.update_slash_menu(self.text)  # type: ignore[attr-defined]
        except Exception:
            pass

    async def _on_key(self, event: events.Key) -> None:
        app = self.app
        if getattr(app, "slash_menu_visible", False):
            if event.key in ("up", "down"):
                event.prevent_default()
                event.stop()
                app.move_slash_menu(-1 if event.key == "up" else 1)  # type: ignore[attr-defined]
                return
            if event.key in ("tab", "enter", "ctrl+m"):
                command = app.selected_slash_command()  # type: ignore[attr-defined]
                if event.key in ("enter", "ctrl+m") and self.text.strip() == command:
                    app.hide_slash_menu()  # type: ignore[attr-defined]
                    event.prevent_default()
                    event.stop()
                    await self.app.submit_prompt()  # type: ignore[attr-defined]
                    return
                event.prevent_default()
                event.stop()
                app.complete_slash_menu()  # type: ignore[attr-defined]
                return
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                app.hide_slash_menu()  # type: ignore[attr-defined]
                if self.text.strip() == "/":
                    self.text = ""
                return
        if event.key in ("enter", "ctrl+m"):
            event.prevent_default()
            event.stop()
            await self.app.submit_prompt()  # type: ignore[attr-defined]
            return
        if event.key in ("shift+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        if event.key in ("ctrl+shift+v", "ctrl+v"):
            try:
                if app._paste_system_clipboard():  # type: ignore[attr-defined]
                    event.prevent_default()
                    event.stop()
                    return
            except Exception:
                pass
        await super()._on_key(event)


class ToolCard(Vertical):
    """A compact tool row with a collapsible output body."""

    def __init__(self, name: str, call_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tool_name = name or "tool"
        self.call_id = call_id
        self.status = "running"
        self.duration_ms = 0
        self._started_at = time.monotonic()
        self._body = Static("", classes="tool-body")
        self._collapse = Collapsible(self._body, title=self._title(), collapsed=True)
        self.add_class("tool-card")
        self.add_class("running")

    def compose(self) -> ComposeResult:
        yield self._collapse

    def _title(self) -> str:
        icon = {"running": "◐", "success": "✓", "error": "✗", "stopped": "■"}.get(self.status, "◐")
        duration = f" · {self.duration_ms / 1000:.1f}s" if self.duration_ms else ""
        return f"{icon} {self.tool_name} · {self.status}{duration}"

    def tick(self) -> None:
        if self.status != "running":
            return
        elapsed = max(0.0, time.monotonic() - self._started_at)
        frame = TOOL_FRAMES[int(elapsed * 12) % len(TOOL_FRAMES)]
        title = f"{frame} {self.tool_name} · running {elapsed:.1f}s"
        self._collapse.title = _shimmer_text(title, elapsed * 0.9)

    def update_status(self, status: str = "", duration_ms: int = 0) -> None:
        previous = self.status
        if status:
            self.status = status
        if self.status == "running" and previous != "running":
            self._started_at = time.monotonic()
        if duration_ms:
            self.duration_ms = duration_ms
        if self.status in ("success", "error") and not self.duration_ms:
            self.duration_ms = int((time.monotonic() - self._started_at) * 1000)
        for css in ("running", "success", "error", "stopped"):
            self.remove_class(css)
        self.add_class(self.status if self.status in ("success", "error", "stopped") else "running")
        self._collapse.title = self._title()

    def stop(self) -> None:
        if self.status != "running":
            return
        self.status = "stopped"
        self.remove_class("running")
        self.add_class("stopped")
        self._collapse.title = f"■ {self.tool_name} · stopped"

    def set_output(self, content: str) -> None:
        content = _plain(content or "")
        if len(content) > 12000:
            content = content[:12000] + "\n… (output truncated in TUI)"
        self._body.update(Text(content))


class ListScreen(ModalScreen[Optional[str]]):
    """Searchable option list used for sessions, models, settings, help, usage."""

    BINDINGS = [Binding("escape", "dismiss_screen", "Close", show=False)]

    def __init__(
        self,
        title: str,
        items: List[Dict[str, str]],
        hint: str = "↑↓ select · Enter confirm · Esc close",
        filter_placeholder: str = "Filter…",
        filterable: bool = True,
        compact: bool = False,
    ) -> None:
        super().__init__()
        self.add_class("modal-screen")
        self.title = title
        self.items = items
        self.hint = hint
        self.filter_placeholder = filter_placeholder
        self.filterable = filterable
        self.compact = compact
        self._visible: List[Dict[str, str]] = list(items)

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-panel"):
            yield Static(self.title, classes="modal-title")
            if self.filterable:
                yield Input(placeholder=self.filter_placeholder, id="list-filter", classes="modal-filter")
            yield OptionList(id="list-options")
            yield Static(self.hint, classes="modal-hint")

    async def on_mount(self) -> None:
        self._populate("")
        self.query_one("#list-filter", Input).focus() if self.filterable else self.query_one("#list-options", OptionList).focus()

    def _populate(self, query: str) -> None:
        query = query.strip().lower()
        self._visible = [
            item for item in self.items
            if not query or query in (item.get("label", "") + " " + item.get("desc", "")).lower()
        ]
        options = self.query_one("#list-options", OptionList)
        options.clear_options()
        for index, item in enumerate(self._visible):
            label = Text(item.get("label", ""), style="bold #e6edf3")
            desc = item.get("desc", "")
            prompt: Any = label
            if desc and self.compact:
                prompt = Text.assemble(label, "  ", (desc, "#8b949e"))
            elif desc:
                prompt = Text.assemble(label, "\n", (desc, "#6e7681"))
            options.add_option(Option(prompt, id=str(index)))
        if self._visible:
            options.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._choose()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._choose()

    def _choose(self) -> None:
        if not self._visible:
            self.dismiss(None)
            return
        options = self.query_one("#list-options", OptionList)
        index = options.highlighted or 0
        index = max(0, min(index, len(self._visible) - 1))
        self.dismiss(self._visible[index].get("id", ""))

    def on_key(self, event: events.Key) -> None:
        if event.key == "down" and self.filterable:
            focused = self.focused
            if isinstance(focused, Input):
                event.prevent_default()
                event.stop()
                self.query_one("#list-options", OptionList).focus()
        elif event.key == "up" and self.filterable:
            focused = self.focused
            options = self.query_one("#list-options", OptionList)
            if focused is options and (options.highlighted or 0) == 0:
                event.prevent_default()
                event.stop()
                self.query_one("#list-filter", Input).focus()

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class SettingsScreen(ListScreen):
    BINDINGS = [
        Binding("escape", "dismiss_screen", "Close", show=False),
        Binding("e", "edit_config", "Edit YAML", show=True),
    ]

    def __init__(self, title: str, items: List[Dict[str, str]], **kwargs: Any) -> None:
        kwargs.setdefault("compact", True)
        super().__init__(title, items, **kwargs)

    def action_edit_config(self) -> None:
        self.dismiss("__edit__")


class UsageScreen(ListScreen):
    pass


class HelpScreen(ListScreen):
    pass


class SetupScreen(ModalScreen[None]):
    """Scrollable, copy-friendly LLM configuration guide."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    def __init__(self, config_path: str, project: Path, reason: str = "") -> None:
        super().__init__()
        self.add_class("modal-screen")
        self.config_path = config_path
        self.project = project
        self.reason = reason

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-panel setup-panel"):
            yield Static("LLM setup  ·  configure a provider", classes="modal-title")
            with VerticalScroll(id="setup-body"):
                yield Markdown(self._guide())
            yield Static("Esc close · /settings then e edits YAML · /reload after editing", classes="modal-hint")

    def _guide(self) -> str:
        reason = f"**Reason:** {self.reason}\n\n" if self.reason else ""
        return f"""## LLM is not configured

Config: `{self.config_path}`

{reason}### A. Interactive setup (recommended)

1. Press `Ctrl+Q` to leave the TUI.
2. Run:

```bash
python3 -m aacode init
```

Choose a provider/model and paste the API key. Then start the TUI again.

### B. Edit the config file

Config file:

```text
{self.config_path}
```

Minimal example:

```yaml
model:
  default_model: deepseek
  models:
    deepseek:
      name: deepseek-chat
      base_url: https://api.deepseek.com/v1
      gateway: openai
      api_key: sk-your-key
```

After saving, run `/reload` inside the TUI.

### C. Environment variables

```bash
export LLM_API_KEY=sk-your-key
export LLM_API_URL=https://api.deepseek.com/v1
export LLM_MODEL_NAME=deepseek-chat
```

Then restart AACode.

### Still getting 401?

A project `.env` file can contain an old key. Check:

```text
{self.project / '.env'}
```

Remove or update `LLM_API_KEY` there, then run `/reload` or restart.
"""

    def action_close(self) -> None:
        self.dismiss(None)


class SetupFormScreen(ModalScreen[None]):
    """Direct LLM configuration form used by /setup and auth failures."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    def __init__(self, config_path: str, project: Path, reason: str = "") -> None:
        super().__init__()
        self.add_class("modal-screen")
        self.config_path = config_path
        self.project = project
        self.reason = reason
        try:
            from aacode.config import settings
            self.default_name = str(settings.model.name or "deepseek-chat")
            self.default_base = str(settings.model.base_url or "https://api.deepseek.com/v1")
            self.default_gateway = str(settings.model.gateway or "openai")
        except Exception:
            self.default_name = "deepseek-chat"
            self.default_base = "https://api.deepseek.com/v1"
            self.default_gateway = "openai"

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-panel setup-panel"):
            yield Static("LLM setup  ·  fill in a provider", classes="modal-title")
            yield Static(self.reason, id="setup-note", classes="setup-note")
            yield Static("Model name", classes="setup-label")
            yield Input(value=self.default_name, id="setup-name", placeholder="deepseek-chat")
            yield Static("Base URL", classes="setup-label")
            yield Input(value=self.default_base, id="setup-base", placeholder="https://api.deepseek.com/v1")
            yield Static("Gateway (openai / anthropic)", classes="setup-label")
            yield Input(value=self.default_gateway, id="setup-gateway", placeholder="openai")
            yield Static("API Key", classes="setup-label")
            yield Input(password=True, id="setup-key", placeholder="sk-...")
            yield Static("Config file", classes="setup-label")
            yield Static(self.config_path, classes="setup-path")
            with Horizontal(classes="setup-actions"):
                yield Button("Save", id="setup-save", variant="primary")
                yield Button("Cancel", id="setup-cancel")
            yield Static("Esc close · aacode init is still available from the shell", classes="modal-hint")

    async def on_mount(self) -> None:
        self.query_one("#setup-name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-cancel":
            self.dismiss(None)
            return
        if event.button.id != "setup-save":
            return
        name = self.query_one("#setup-name", Input).value.strip()
        base_url = self.query_one("#setup-base", Input).value.strip()
        gateway = self.query_one("#setup-gateway", Input).value.strip().lower()
        api_key = self.query_one("#setup-key", Input).value.strip()
        if not name or not base_url or not api_key:
            self.query_one("#setup-note", Static).update("Model name, Base URL, and API Key are required.")
            return
        if gateway not in ("openai", "anthropic"):
            self.query_one("#setup-note", Static).update("Gateway must be 'openai' or 'anthropic'.")
            return
        try:
            self.app.save_llm_config(name, base_url, gateway, api_key)  # type: ignore[attr-defined]
        except Exception as exc:
            self.query_one("#setup-note", Static).update(f"Could not save: {exc}")
            return
        self.app.notify("LLM configured", timeout=2)  # type: ignore[attr-defined]
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class AACodeCommands(Provider):
    """Commands available in Textual's built-in Ctrl+P palette."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = self.app
        commands = [
            ("Help", "Show keyboard shortcuts and commands", app.action_help),
            ("Sessions", "Resume a previous session", app.action_sessions),
            ("Models", "Switch the model for the next task", app.action_models),
            ("Settings", "Inspect context and agent settings", app.action_settings),
            ("Setup LLM", "Show provider/API-key configuration help", app.action_setup),
            ("Usage", "Show context, cache, token, and cost details", app.action_usage),
            ("Compact session", "Prune and summarize the current session", app.action_compact),
            ("Clear transcript", "Clear the visible transcript", app.action_clear),
            ("Toggle tool output", "Expand or collapse tool output", app.action_toggle_tools),
            ("Toggle thinking", "Show or hide reasoning blocks", app.action_toggle_thinking),
            ("Cancel task", "Interrupt the running task", app.action_cancel),
            ("Quit", "Close AACode", app.action_quit),
        ]
        for name, help_text, callback in commands:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), callback, text=name, help=help_text)

    async def discover(self) -> Hits:
        app = self.app
        commands = [
            ("Help", "Show keyboard shortcuts and commands", app.action_help),
            ("Sessions", "Resume a previous session", app.action_sessions),
            ("Models", "Switch the model for the next task", app.action_models),
            ("Settings", "Inspect context and agent settings", app.action_settings),
            ("Setup LLM", "Show provider/API-key configuration help", app.action_setup),
            ("Usage", "Show context, cache, token, and cost details", app.action_usage),
            ("Compact session", "Prune and summarize the current session", app.action_compact),
            ("Clear transcript", "Clear the visible transcript", app.action_clear),
            ("Toggle tool output", "Expand or collapse tool output", app.action_toggle_tools),
            ("Toggle thinking", "Show or hide reasoning blocks", app.action_toggle_thinking),
            ("Cancel task", "Interrupt the running task", app.action_cancel),
            ("Quit", "Close AACode", app.action_quit),
        ]
        for name, help_text, callback in commands:
            yield DiscoveryHit(name, callback, help=help_text)


class TuiApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "AACode"
    COMMANDS = App.COMMANDS | {AACodeCommands}
    BINDINGS = [
        Binding("ctrl+k", "command_palette", "Commands", priority=True, show=True),
        Binding("ctrl+o", "toggle_tools", "Tool output", show=False),
        Binding("ctrl+t", "toggle_thinking", "Thinking", show=False),
        Binding("ctrl+l", "clear", "Clear", show=False),
        Binding("ctrl+y", "copy_output", "Copy output", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, project: Path, session: str = "", model: str = ""):
        super().__init__()
        self.project = project.absolute()
        self.workdir = self.project
        self.session_id = session
        self.model = model
        self.worker = Worker(self.project, self.workdir)
        self.usage: Dict[str, Any] = {}
        self.context_tokens = 0
        self.context_window = 0
        self.cache_rate: Optional[float] = None
        self.cost: Optional[float] = None
        self.currency = ""
        self.status = "idle"
        self.history: List[str] = []
        self.history_index = -1
        self.show_tools = True
        self.show_thinking = True
        self._spinner = 0
        self._last_error = ""
        self._assistant_widget: Optional[Markdown] = None
        self._assistant_text = ""
        self._assistant_dirty = False
        self._assistant_streaming = False
        self._thinking_label: Optional[Static] = None
        self._thinking_widget: Optional[Markdown] = None
        self._thinking_text = ""
        self._thinking_dirty = False
        self._thinking_streaming = False
        self._active_tool = ""
        self._phase = ""
        self._slash_visible = False
        self._tool_cards: Dict[str, ToolCard] = {}
        self._progress_cards: Dict[str, ToolCard] = {}
        self._splash: Optional[Vertical] = None
        self._splash_title: Optional[Static] = None
        self._launch_widget: Optional[Static] = None
        self._launch_started = time.monotonic()
        self._follow_output = True
        self._started = time.monotonic()
        self._last_flush = 0.0
        self._event_task: Optional[asyncio.Task[Any]] = None
        self._closing = False

    # ── layout ───────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("", id="brand")
            yield Static("", id="header-right")
        yield VerticalScroll(id="transcript")
        with Vertical(id="footer"):
            yield OptionList(id="slash-menu")
            yield Composer(id="prompt", placeholder=" Ask AACode…")
            with Horizontal(id="statusline"):
                yield Static("", id="status-left")
                yield Static("", id="status-right")

    async def on_mount(self) -> None:
        self._refresh_header()
        self._refresh_status()
        self._splash_title = Static(Text("AACode", style="bold #e6edf3"), classes="title")
        self._launch_widget = Static(Text("▱" * 22, style="#30363d"), classes="launch")
        self._launch_started = time.monotonic()
        splash_children = [
            self._splash_title,
            Static(Text(f"AI coding agent · v{__version__}", style="#8b949e"), classes="subtitle"),
            Static(Text(str(self.project), style="#6e7681"), classes="path"),
            self._launch_widget,
        ]
        if not self._has_api_key():
            splash_children.append(
                Static(Text("⚠ No LLM API key configured · type /setup for help", style="bold #d29922"), classes="warning")
            )
        splash_children.extend([
            Static(Text("Try one of these:", style="bold #8b949e"), classes="section"),
            Static(Text("  › Explain the architecture of this project", style="#c9d1d9"), classes="example"),
            Static(Text("  › Run the test suite and fix any failures", style="#c9d1d9"), classes="example"),
            Static(Text("  › Add a feature and update the documentation", style="#c9d1d9"), classes="example"),
            Static(Text("/help commands · Ctrl+K command palette · Shift+Enter newline", style="#6e7681"), classes="hint"),
        ])
        self._splash = Vertical(*splash_children, classes="splash")
        await self.transcript.mount(self._splash)
        menu = self.query_one("#slash-menu", OptionList)
        menu.display = False
        menu.can_focus = False
        self.query_one("#prompt", Composer).focus()
        self._event_task = asyncio.create_task(self._event_loop())
        self.set_interval(0.08, self._tick)

    async def on_unmount(self) -> None:
        self._closing = True
        if self._event_task:
            self._event_task.cancel()
        self.worker.cancel()

    @property
    def transcript(self) -> VerticalScroll:
        return self.query_one("#transcript", VerticalScroll)

    # ── status/header ────────────────────────────────────────────
    def _refresh_header(self) -> None:
        brand = self.query_one("#brand", Static)
        right = self.query_one("#header-right", Static)
        brand_text = Text.assemble(("AACode", "bold #e6edf3"), ("  ·  ", "#30363d"), (self.project.name, "#8b949e"))
        brand_text.no_wrap = True
        brand_text.overflow = "ellipsis"
        brand.update(brand_text)
        sid = self.session_id
        parts = [self.model or "default model"]
        if sid:
            parts.append(sid)
        if self.status == "running":
            pulse = WORK_COLORS[self._spinner % len(WORK_COLORS)]
            right.update(Text.assemble((f"{WORK_FRAMES[self._spinner % len(WORK_FRAMES)]} ", pulse), (" · ".join(parts), "#6e7681"), no_wrap=True, overflow="ellipsis"))
        else:
            right.update(Text(" · ".join(parts), style="#6e7681", no_wrap=True, overflow="ellipsis"))

    def _status_suffix(self) -> str:
        parts: List[str] = []
        if self.context_window:
            pct = min(100, round(self.context_tokens / self.context_window * 100))
            parts.append(f"ctx {format_tokens(self.context_tokens)} ({pct}%)")
        elif self.context_tokens:
            parts.append(f"ctx {format_tokens(self.context_tokens)}")
        if self.cache_rate is not None:
            parts.append(f"cache {self.cache_rate:.0%}")
        if self.usage:
            parts.append(
                f"↑{format_tokens(int(self.usage.get('prompt_total', 0) or 0))} "
                f"↓{format_tokens(int(self.usage.get('output', 0) or 0))}"
            )
            if self.cost is not None:
                parts.append(format_cost(self.cost, self.currency))
        return " · ".join(parts)

    def _refresh_status(self) -> None:
        left = self.query_one("#status-left", Static)
        right = self.query_one("#status-right", Static)
        if self.status == "running":
            frame = WORK_FRAMES[self._spinner % len(WORK_FRAMES)]
            color = WORK_COLORS[self._spinner % len(WORK_COLORS)]
            elapsed = max(0.0, time.monotonic() - self._started)
            name = self._active_tool or self._phase or "Working"
            if not self._active_tool:
                name += "." * (1 + (self._spinner // 4) % 3)
            label = f"{frame} {name} {elapsed:.1f}s · Esc"
            shimmer = _shimmer_text(label, elapsed * 0.8, base=color, highlight="#fff2b0")
            shimmer.no_wrap = True
            shimmer.overflow = "ellipsis"
            left.update(shimmer)
        elif self.status == "error":
            left.update(Text("✗ Error · Ctrl+K · /help · Ctrl+Q quit", style="#f85149", no_wrap=True, overflow="ellipsis"))
        else:
            if self.size.width < 100:
                hint = "Enter · /help · Esc · ^Q quit"
            else:
                hint = "Enter send · /help · Ctrl+K · Esc cancel · Ctrl+Q quit · Ctrl+C copy"
            left.update(Text(hint, style="#6e7681", no_wrap=True, overflow="ellipsis"))
        suffix = self._status_suffix()
        right.update(Text(suffix, style="#6e7681", no_wrap=True, overflow="ellipsis"))

    async def _tick(self) -> None:
        self._spinner += 1
        if self._closing:
            return
        if self._splash_title is not None and self._splash is not None and self._splash.display:
            self._splash_title.update(_shimmer_text("AACode", self._spinner / 26, "#e6edf3", "#ffffff"))
        if self._launch_widget is not None and self._launch_widget.display:
            elapsed = time.monotonic() - self._launch_started
            if elapsed >= 1.15:
                self._launch_widget.display = False
            else:
                filled = max(1, int((elapsed / 1.15) * 22))
                rail = "▰" * filled + "▱" * (22 - filled)
                self._launch_widget.update(Text(rail, style="#4c8dff"))
        running_cards = [card for card in self.query(ToolCard) if card.status == "running"]
        if (
            self.status != "running"
            and not self._assistant_streaming
            and not self._thinking_streaming
            and not running_cards
        ):
            return
        if self.status == "running":
            self._refresh_header()
            self._refresh_status()
            if self._follow_output:
                # Markdown blocks mount/layout asynchronously; re-issue the
                # scroll after layout so streaming output keeps following.
                self.call_after_refresh(lambda: self.transcript.scroll_end(animate=False, immediate=True))
        for card in running_cards:
            card.tick()
        if self._thinking_streaming and self._thinking_label is not None and self.show_thinking:
            dots = "." * (1 + (self._spinner // 4) % 3)
            label = _shimmer_text(f"Thinking{dots}", self._spinner / 20, "#6e7681", "#c9d1d9")
            label.stylize("italic")
            self._thinking_label.update(label)

    def _set_running(self, running: bool) -> None:
        self.status = "running" if running else "idle"
        self._refresh_status()

    def _finish_streaming(self) -> None:
        self._assistant_streaming = False
        self._thinking_streaming = False
        self._active_tool = ""
        self._phase = ""
        if self._assistant_widget is not None:
            self._assistant_dirty = True
        if self._thinking_label is not None:
            self._thinking_label.update(Text("Thinking", style="italic #6e7681"))
        for card in self.query(ToolCard):
            card.stop()

    # ── entries ──────────────────────────────────────────────────
    async def _add_user(self, text: str) -> None:
        if self._splash is not None:
            self._splash.display = False
        user_widget = Static(Text.assemble(("› ", "bold #4c8dff"), (text, "#e6edf3")), classes="msg-user")
        await self.transcript.mount(user_widget)
        self._assistant_widget = None
        self._assistant_streaming = False
        self._thinking_widget = None
        self._thinking_label = None
        self._thinking_streaming = False
        self._active_tool = ""
        self._phase = ""
        self._scroll_end(force=True)

    async def _add_notice(self, text: str) -> None:
        await self.transcript.mount(Static(Text(f"· {_plain(text)}", style="#6e7681"), classes="system"))
        self._scroll_end()

    async def _add_done(self, text: str) -> None:
        await self.transcript.mount(Static(Text(text, style="#3fb950"), classes="done"))
        self._scroll_end(force=True)

    async def _add_error(self, text: str) -> None:
        await self.transcript.mount(Static(Text(f"✗ {_plain(text)}", style="#f85149"), classes="error-text"))
        self._scroll_end(force=True)

    async def _ensure_assistant(self) -> Markdown:
        if self._assistant_widget is None:
            widget = Markdown("", classes="msg-assistant")
            await self.transcript.mount(widget)
            self._assistant_widget = widget
            self._assistant_text = ""
            self._assistant_dirty = False
        return self._assistant_widget

    async def _ensure_thinking(self) -> tuple[Static, Markdown]:
        if self._thinking_widget is None or self._thinking_label is None:
            label = Static(Text("Thinking", style="italic #6e7681"), classes="thinking-label")
            widget = Markdown("", classes="msg-thinking")
            await self.transcript.mount(label)
            await self.transcript.mount(widget)
            self._thinking_label = label
            self._thinking_widget = widget
            self._thinking_text = ""
            self._thinking_dirty = False
            self._thinking_streaming = True
            label.display = self.show_thinking
            widget.display = self.show_thinking
        return self._thinking_label, self._thinking_widget

    async def _tool_card(self, call_id: str, name: str) -> ToolCard:
        card = self._tool_cards.get(call_id)
        if card is None:
            self._assistant_streaming = False
            self._thinking_streaming = False
            self._assistant_dirty = True
            self._active_tool = name
            await self._flush_stream(force=True)
            self._assistant_widget = None
            self._thinking_widget = None
            self._thinking_label = None
            card = ToolCard(name, call_id)
            self._tool_cards[call_id] = card
            await self.transcript.mount(card)
            self._scroll_end()
        return card

    async def _resolve_tool_card(self, call_id: str, name: str) -> ToolCard:
        """Reuse the progress card when tool_status/tool_result arrives.

        main_agent emits ``tool_progress`` without a call_id, while the
        structured React events carry one. Without re-keying, the progress card
        is left behind and later marked ``stopped`` even though the tool
        succeeded.
        """
        card = self._tool_cards.get(call_id)
        if card is not None:
            return card
        progress = self._progress_cards.pop(name, None)
        if progress is not None:
            self._tool_cards.pop(progress.call_id, None)
            progress.call_id = call_id
            self._tool_cards[call_id] = progress
            return progress
        return await self._tool_card(call_id, name)

    def _scroll_end(self, force: bool = False) -> None:
        if force:
            self._follow_output = True
        if self._follow_output:
            self.call_after_refresh(lambda: self.transcript.scroll_end(animate=False, immediate=True))

    def _sync_follow(self) -> None:
        try:
            self._follow_output = self.transcript.is_vertical_scroll_end
        except Exception:
            pass

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._follow_output = False

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.call_after_refresh(self._sync_follow)

    def _assistant_display(self) -> str:
        return self._assistant_text

    async def _flush_stream(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < 0.08:
            return
        if self._assistant_dirty and self._assistant_widget is not None:
            await self._assistant_widget.update(self._assistant_display())
            self._assistant_dirty = False
            self._scroll_end()
        if self._thinking_dirty and self._thinking_widget is not None:
            await self._thinking_widget.update(self._thinking_text)
            self._thinking_dirty = False
            self._scroll_end()
        self._last_flush = now

    # ── worker events ────────────────────────────────────────────
    async def _event_loop(self) -> None:
        while not self._closing:
            got = False
            while True:
                try:
                    event = self.worker.events.get_nowait()
                except queue.Empty:
                    break
                got = True
                try:
                    await self._handle_event(event)
                except Exception as exc:  # never let a UI event kill the TUI
                    await self._add_error(f"TUI event error: {exc}")
            if got:
                await self._flush_stream(force=True)
            else:
                await self._flush_stream()
            await asyncio.sleep(0.04)

    async def _handle_event(self, event: Dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "worker_ready":
            self.session_id = event.get("session_id") or self.session_id
            if event.get("model"):
                self.model = event.get("model")
            self._refresh_header()
            self._set_running(True)
        elif kind == "phase":
            self._phase = str(event.get("label") or "")
            self._refresh_status()
        elif kind == "text_delta":
            text = _plain(event.get("text", ""))
            if not text:
                return
            self._phase = ""
            if event.get("kind") == "thinking":
                label, widget = await self._ensure_thinking()
                self._thinking_streaming = True
                self._thinking_text += text
                self._thinking_dirty = True
                label.display = self.show_thinking
                widget.display = self.show_thinking
            else:
                widget = await self._ensure_assistant()
                self._assistant_streaming = True
                self._thinking_streaming = False
                if self._thinking_label is not None:
                    self._thinking_label.update(Text("Thinking", style="italic #6e7681"))
                self._cursor_on = True
                self._assistant_text += text
                self._assistant_dirty = True
        elif kind == "tool_progress":
            name = event.get("name") or event.get("tool") or "tool"
            call_id = event.get("call_id")
            if call_id:
                card = await self._tool_card(call_id, name)
            else:
                card = self._progress_cards.get(name)
                if card is None:
                    card = await self._tool_card(f"progress:{name}", name)
                    self._progress_cards[name] = card
            self._active_tool = name
            self._phase = ""
            self._refresh_status()
            card.update_status("running")
        elif kind == "tool_status":
            call_id = event.get("call_id", "")
            name = event.get("tool") or event.get("name") or "tool"
            card = await self._resolve_tool_card(call_id, name)
            card.update_status(event.get("status") or "", int(event.get("duration_ms") or 0))
        elif kind == "tool_result":
            call_id = event.get("call_id", "")
            name = event.get("tool") or event.get("name") or "tool"
            card = await self._resolve_tool_card(call_id, name)
            card.update_status(event.get("status") or "success", int(event.get("duration_ms") or 0))
            if event.get("content"):
                card.set_output(str(event.get("content")))
            self._active_tool = ""
            self._thinking_streaming = False
            self._refresh_status()
            self._scroll_end()
        elif kind == "usage":
            self.usage = event.get("usage") or {}
            self.context_tokens = int(event.get("context_tokens") or self.context_tokens)
            self.context_window = int(event.get("context_window") or self.context_window)
            self.cache_rate = event.get("cache_hit_rate")
            self.cost = event.get("cost")
            self.currency = event.get("currency") or self.currency
            self._refresh_status()
        elif kind == "compaction":
            await self._add_notice(
                f"Compaction: {event.get('pruned', 0)} tool results pruned, "
                f"summary={'yes' if event.get('summary') else 'no'}, "
                f"context ~{format_tokens(int(event.get('tokens') or 0))} tokens"
            )
        elif kind == "repeat_reminder":
            await self._add_notice(str(event.get("text", "Repeated tool call detected.")))
        elif kind == "tool_spill":
            await self._add_notice(
                f"Spilled {event.get('tool')} output ({event.get('original_chars', 0)} chars) to {event.get('path')}"
            )
        elif kind == "task_start":
            self._set_running(True)
            if event.get("session_id"):
                self.session_id = event.get("session_id")
                self._refresh_header()
        elif kind == "task_end":
            self._finish_streaming()
            await self._flush_stream(force=True)
            self._set_running(False)
            status = event.get("status", "idle")
            if status != "completed":
                await self._add_notice(f"Task {status}.")
        elif kind == "compact_done":
            self._set_running(False)
            result = event.get("result") or {}
            if result.get("status") == "compacted":
                await self._add_done(
                    f"✓ Compacted · cutoff {result.get('cutoff_before')} → {result.get('cutoff_after')} · "
                    f"~{format_tokens(int(result.get('tokens') or 0))} tokens"
                    + (" · summary" if result.get("summary") else "")
                )
            else:
                await self._add_notice(f"Compaction: {result.get('status', 'noop')}")
        elif kind == "worker_done":
            self._finish_streaming()
            await self._flush_stream(force=True)
            self._set_running(False)
            result = event.get("result") or {}
            status = str(result.get("status") or "completed")
            usage = event.get("usage") or {}
            if usage:
                self.usage = usage
            elapsed = int(result.get("execution_time") or result.get("total_time") or 0)
            if not elapsed:
                elapsed = int(time.monotonic() - self._started)
            tokens = int(self.usage.get("prompt_total", 0) or 0) + int(self.usage.get("output", 0) or 0)
            if status == "completed":
                await self._add_done(f"✓ Task completed · {elapsed}s · {format_tokens(tokens)} tokens")
            else:
                detail = str(result.get("error") or result.get("final_thought") or status)
                await self._add_error(f"Task failed: {detail}")
                lowered = detail.lower()
                if any(marker in lowered for marker in ("401", "authentication", "api key", "unauthorized", "invalid")):
                    await self._add_notice("The configured API key was rejected. Run /setup to fix it.")
                    self.action_setup("The configured API key was rejected (401). If you just updated the config, check for a stale .env file.")
            self._refresh_status()
        elif kind == "worker_error":
            self._finish_streaming()
            await self._flush_stream(force=True)
            self._set_running(False)
            self._last_error = str(event.get("error") or "unknown error")
            await self._add_error(self._last_error)
        elif kind == "worker_cancelled":
            self._finish_streaming()
            await self._flush_stream(force=True)
            self._set_running(False)
            await self._add_notice("Task cancelled.")
        elif kind == "worker_exit":
            self._finish_streaming()
            await self._flush_stream(force=True)
            if self.status == "running":
                self._set_running(False)
            self._assistant_widget = None
            self._thinking_widget = None
            self._thinking_label = None
        elif kind == "session_switched":
            if event.get("ok"):
                self.session_id = event.get("session_id") or self.session_id
                self._refresh_header()

    def _has_api_key(self) -> bool:
        try:
            from aacode.config import settings
            profile = settings.get_model_profile(self.model)
            return bool(profile.get("api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
        except Exception:
            return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))

    def save_llm_config(self, name: str, base_url: str, gateway: str, api_key: str) -> str:
        """Persist one model route to the YAML config and reload it."""
        from aacode.config import settings

        path = Path(getattr(settings, "config_path", "") or "").expanduser()
        if not path:
            import platformdirs
            path = Path(platformdirs.user_config_dir("com.aacode", roaming=True)) / "aacode_config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        model_section = data.get("model") if isinstance(data.get("model"), dict) else {}
        models = model_section.get("models") if isinstance(model_section.get("models"), dict) else {}
        key = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "custom"
        entry = models.get(key) if isinstance(models.get(key), dict) else {}
        from aacode.config import DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS
        entry.setdefault("context_window", DEFAULT_CONTEXT_WINDOW)
        entry.setdefault("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
        entry.update({"name": name, "base_url": base_url, "gateway": gateway, "api_key": api_key})
        models[key] = entry
        model_section["models"] = models
        model_section["default_model"] = key
        data["model"] = model_section
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        # Make the current TUI/next worker use the just-saved route immediately.
        os.environ["LLM_MODEL_NAME"] = name
        os.environ["LLM_API_URL"] = base_url
        os.environ["LLM_GATEWAY"] = gateway
        os.environ["LLM_API_KEY"] = api_key
        settings.load_config()
        self.model = name
        self._refresh_header()
        self._refresh_status()
        return str(path)

    def action_setup(self, reason: str = "") -> None:
        try:
            from aacode.config import settings
            config_path = str(getattr(settings, "config_path", "") or "~/.config/com.aacode/aacode_config.yaml")
        except Exception:
            config_path = "~/.config/com.aacode/aacode_config.yaml"
        self.push_screen(SetupFormScreen(config_path, self.project, reason=reason))

    # ── slash menu ───────────────────────────────────────────────
    @property
    def slash_menu_visible(self) -> bool:
        return self._slash_visible

    def _slash_menu(self) -> OptionList:
        return self.query_one("#slash-menu", OptionList)

    def update_slash_menu(self, text: str) -> None:
        if not self.is_mounted:
            return
        value = text or ""
        query = value.strip()
        if not query.startswith("/") or " " in query or "\n" in query or value != query:
            self.hide_slash_menu()
            return
        needle = query[1:].lower()
        matches = [(cmd, desc) for cmd, desc in SLASH_COMMANDS if needle in cmd[1:].lower()]
        if not matches:
            self.hide_slash_menu()
            return
        menu = self._slash_menu()
        menu.clear_options()
        for cmd, desc in matches:
            menu.add_option(Option(Text.assemble((cmd, "bold #e6edf3"), "  ", (desc, "#8b949e")), id=cmd))
        menu.highlighted = 0
        menu.display = True
        self._slash_visible = True

    def hide_slash_menu(self) -> None:
        if not self.is_mounted:
            self._slash_visible = False
            return
        self._slash_visible = False
        try:
            menu = self._slash_menu()
            menu.display = False
            menu.clear_options()
        except Exception:
            pass

    def move_slash_menu(self, delta: int) -> None:
        if not self._slash_visible:
            return
        menu = self._slash_menu()
        count = menu.option_count
        if count:
            menu.highlighted = max(0, min(count - 1, (menu.highlighted or 0) + delta))

    def selected_slash_command(self) -> str:
        menu = self._slash_menu()
        option = menu.highlighted_option
        return str(option.id) if option is not None and option.id else ""

    def complete_slash_menu(self) -> None:
        command = self.selected_slash_command()
        if not command:
            return
        prompt = self.query_one("#prompt", Composer)
        prompt.text = command + " "
        try:
            prompt.move_cursor((0, len(command) + 1))
        except Exception:
            pass
        self.hide_slash_menu()
        prompt.focus()

    # ── prompt/commands ──────────────────────────────────────────
    async def submit_prompt(self) -> None:
        prompt = self.query_one("#prompt", Composer)
        text = prompt.text.strip()
        if not text:
            return
        prompt.text = ""
        if text.startswith("/"):
            await self._run_command(text)
            prompt.focus()
            return
        if self.worker.running():
            await self._add_notice("A task is already running. Press Esc to cancel it first.")
            prompt.focus()
            return
        if not self._has_api_key():
            await self._add_error("No LLM API key is configured.")
            self.action_setup("No API key is configured for the selected model.")
            prompt.focus()
            return
        self.history.append(text)
        self.history_index = -1
        await self._add_user(text)
        self._started = time.monotonic()
        self._set_running(True)
        self.worker.start(text, self.session_id, self.model)
        prompt.focus()

    async def _run_command(self, text: str) -> None:
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if not parts:
            return
        cmd = parts[0].lower()
        if cmd in ("/help", "/h", "/?"):
            self.action_help()
        elif cmd in ("/usage", "/cost", "/tokens"):
            self.action_usage()
        elif cmd in ("/sessions", "/session"):
            self.action_sessions()
        elif cmd == "/resume":
            if len(parts) > 1:
                self.session_id = parts[1]
                self._refresh_header()
                await self._add_notice(f"Next task will resume session {self.session_id}.")
            else:
                self.action_sessions()
        elif cmd in ("/model", "/models"):
            if len(parts) > 1:
                self.model = parts[1]
                self._refresh_header()
                await self._add_notice(f"Next task will use model {self.model}.")
            else:
                self.action_models()
        elif cmd in ("/settings", "/config"):
            self.action_settings()
        elif cmd == "/setup":
            self.action_setup()
        elif cmd in ("/reload", "/reload-config"):
            try:
                from aacode.config import settings
                settings.load_config()
                self._refresh_header()
                self._refresh_status()
                await self._add_notice("Configuration reloaded.")
            except Exception as exc:
                await self._add_error(f"Config reload failed: {exc}")
        elif cmd == "/copy":
            await self.action_copy_output()
        elif cmd == "/tools":
            await self._toggle_tool_visibility()
        elif cmd == "/thinking":
            await self.action_toggle_thinking()
        elif cmd == "/clear":
            await self.action_clear()
        elif cmd == "/compact":
            await self.action_compact()
        elif cmd == "/cancel":
            await self.action_cancel()
        elif cmd in ("/exit", "/quit", "/q"):
            self.exit()
        else:
            await self._add_notice(f"Unknown command: {cmd}. /help for commands.")

    # ── actions ──────────────────────────────────────────────────
    def action_help(self) -> None:
        items = [
            {"label": "Enter", "desc": "Send the current prompt", "id": ""},
            {"label": "Shift+Enter / Ctrl+J", "desc": "Insert a newline", "id": ""},
            {"label": "Esc", "desc": "Cancel the running task", "id": ""},
            {"label": "Ctrl+K / Ctrl+P", "desc": "Open the command palette", "id": ""},
            {"label": "Ctrl+O", "desc": "Expand or collapse tool output", "id": ""},
            {"label": "Ctrl+T", "desc": "Toggle thinking blocks", "id": ""},
            {"label": "Ctrl+L", "desc": "Clear the transcript", "id": ""},
            {"label": "Ctrl+C", "desc": "Copy the current mouse selection", "id": ""},
            {"label": "Ctrl+Y / /copy", "desc": "Copy the last assistant answer", "id": ""},
            {"label": "Ctrl+V / right-click", "desc": "Paste from the system clipboard", "id": ""},
            {"label": "Ctrl+Q", "desc": "Quit the TUI", "id": ""},
            {"label": "/help /usage /sessions /model", "desc": "Slash commands", "id": ""},
            {"label": "/settings /reload /compact /tools /thinking", "desc": "More slash commands", "id": ""},
            {"label": "/setup /clear /cancel /exit", "desc": "Setup and session controls", "id": ""},
        ]
        self.push_screen(HelpScreen("Help  ·  keyboard & commands", items, hint="Esc / Enter to close", filterable=False))

    def action_usage(self) -> None:
        rate = cache_hit_rate(self.usage) if self.usage else self.cache_rate
        items = [
            {"label": "Calls", "desc": str(self.usage.get("calls", 0)), "id": ""},
            {"label": "Prompt tokens", "desc": format_tokens(int(self.usage.get("prompt_total", 0) or 0)), "id": ""},
            {"label": "Uncached input", "desc": format_tokens(int(self.usage.get("uncached_input", 0) or 0)), "id": ""},
            {"label": "Cache read", "desc": format_tokens(int(self.usage.get("cache_read", 0) or 0)), "id": ""},
            {"label": "Output tokens", "desc": format_tokens(int(self.usage.get("output", 0) or 0)), "id": ""},
            {"label": "Cache hit rate", "desc": f"{rate:.1%}" if rate is not None else "unknown", "id": ""},
            {"label": "Context", "desc": f"{format_tokens(self.context_tokens)} / {format_tokens(self.context_window)}", "id": ""},
            {"label": "Estimated cost", "desc": format_cost(self.cost, self.currency), "id": ""},
        ]
        self.push_screen(UsageScreen("Usage  ·  current session", items, hint="Esc / Enter to close", filterable=False))

    def action_sessions(self) -> None:
        index = self.project / ".aacode" / "sessions" / "sessions_index.json"
        items: List[Dict[str, str]] = []
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            rows = sorted(data.items(), key=lambda kv: str((kv[1] or {}).get("last_activity") or ""), reverse=True)
            for sid, info in rows[:50]:
                info = info or {}
                title = str(info.get("title") or "")[:60]
                when = str(info.get("last_activity") or "")[:19]
                mark = "● " if sid == self.session_id else ""
                items.append({"id": sid, "label": f"{mark}{title or sid}", "desc": f"{sid}  ·  {when}"})
        except Exception as exc:
            items.append({"id": "", "label": f"No session index: {exc}", "desc": ""})
        self.push_screen(
            ListScreen("Sessions  ·  resume a session", items, filter_placeholder="Filter sessions…"),
            self._sessions_chosen,
        )

    async def _sessions_chosen(self, chosen: Optional[str]) -> None:
        if chosen:
            self.session_id = chosen
            self._refresh_header()
            await self._add_notice(f"Next task will resume session {chosen}.")

    def action_models(self) -> None:
        items: List[Dict[str, str]] = []
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
                mark = "● " if name == self.model else ""
                items.append({"id": name, "label": f"{mark}{name}", "desc": f"{key}  ·  window {window}  ·  output {output or 'default'}"})
        except Exception as exc:
            items.append({"id": "", "label": f"Model list unavailable: {exc}", "desc": ""})
        if self.model and not any(item.get("id") == self.model for item in items):
            items.insert(0, {"id": self.model, "label": f"● {self.model}", "desc": "current selection"})
        self.push_screen(
            ListScreen("Models  ·  select for the next task", items, filter_placeholder="Filter models…"),
            self._models_chosen,
        )

    async def _models_chosen(self, chosen: Optional[str]) -> None:
        if chosen:
            self.model = chosen
            self._refresh_header()
            await self._add_notice(f"Next task will use model {chosen}.")

    def action_settings(self) -> None:
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
                ("Prune enabled", str(ctx.prune_enabled)),
                ("Tool profile", str(settings.tools.tool_profile)),
                ("Max iterations", str(settings.agent.max_react_iterations)),
                ("Summary model", str(ctx.summary_model or "(main route)")),
                ("Show tool cards", "on" if self.show_tools else "off"),
                ("Show thinking", "on" if self.show_thinking else "off"),
            ]
        except Exception as exc:
            rows = [("Settings unavailable", str(exc))]
        items = [{"id": key, "label": key, "desc": value} for key, value in rows]
        self.push_screen(
            SettingsScreen(
                "Settings  ·  Enter toggles display rows · e opens YAML in $EDITOR",
                items,
                hint="↑↓ select · Enter toggle · e edit YAML · Esc close",
                filterable=False,
            ),
            self._settings_chosen,
        )

    async def _settings_chosen(self, chosen: Optional[str]) -> None:
        if chosen == "__edit__":
            await self._edit_config()
        elif chosen in ("Show tool cards", "Show thinking"):
            if chosen == "Show tool cards":
                await self._toggle_tool_visibility()
            else:
                await self.action_toggle_thinking()
            self.action_settings()

    async def _edit_config(self) -> None:
        try:
            from aacode.config import settings
            path = getattr(settings, "config_path", None)
        except Exception as exc:
            await self._add_notice(f"Config editor unavailable: {exc}")
            return
        if not path:
            await self._add_notice("No config file path is available.")
            return
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        cmd = shlex.split(editor) + [str(path)]
        try:
            with self.suspend():
                subprocess.run(cmd, check=False)
        except Exception as exc:
            await self._add_notice(f"Could not open editor {editor}: {exc}")
            return
        try:
            settings.load_config()
            await self._add_notice(f"Config reloaded from {path}.")
        except Exception as exc:
            await self._add_notice(f"Config saved, but reload failed: {exc}")
        self._refresh_header()
        self._refresh_status()

    async def action_compact(self) -> None:
        if self.worker.running():
            await self._add_notice("A task is running; cancel it before compacting.")
            return
        await self._add_notice("Compacting the current session…")
        self._set_running(True)
        self.worker.start("", self.session_id, self.model, compact=True)

    async def action_copy_output(self) -> None:
        """Copy the last assistant answer even when mouse selection is awkward."""
        text = ""
        try:
            widgets = list(self.query(".msg-assistant"))
            if widgets:
                text = str(getattr(widgets[-1], "source", "") or "")
        except Exception:
            text = ""
        if not text:
            text = self._assistant_text
        if not text:
            await self._add_notice("Nothing to copy yet.")
            return
        self.copy_to_clipboard(text)
        try:
            self.notify("Copied to clipboard", timeout=1.2)
        except Exception:
            await self._add_notice("Copied to clipboard.")

    async def action_clear(self) -> None:
        await self.transcript.remove_children()
        self._splash = None
        self._assistant_widget = None
        self._thinking_widget = None
        self._thinking_label = None
        self._tool_cards.clear()
        self._progress_cards.clear()
        self._follow_output = True
        await self._add_notice("Transcript cleared.")

    async def action_cancel(self) -> None:
        if self.worker.running():
            self.worker.cancel()
            await self._add_notice("Cancelling task…")
        else:
            self.query_one("#prompt", Composer).text = ""

    def on_text_selected(self, event: events.TextSelected) -> None:
        """Copy-on-select, matching OpenCode's terminal behaviour."""
        try:
            selected = self.screen.get_selected_text()
        except Exception:
            selected = None
        if selected:
            self.copy_to_clipboard(selected)

    def copy_to_clipboard(self, text: str) -> None:
        """Copy via Textual (OSC52) and fall back to the native clipboard.

        Textual's OSC52 path does not work in macOS Terminal.app, so use
        pbcopy/clip/xclip/wl-copy when available.
        """
        try:
            super().copy_to_clipboard(text)
        except Exception:
            pass
        try:
            import subprocess
            if sys.platform == "darwin":
                commands = [["pbcopy"]]
            elif sys.platform.startswith("win"):
                commands = [["clip"]]
            else:
                commands = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
            for command in commands:
                try:
                    result = subprocess.run(command, input=text, text=True, timeout=1.0)
                    if result.returncode == 0:
                        return
                except Exception:
                    continue
        except Exception:
            pass

    def _system_clipboard(self) -> str:
        """Read the OS clipboard best-effort (terminal right-click paste)."""
        import platform
        import subprocess

        commands = []
        if sys.platform == "darwin":
            commands = [["pbpaste"]]
        elif sys.platform.startswith("win"):
            commands = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
        else:
            commands = [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]
        for command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=1.0)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                continue
        return ""

    def _paste_system_clipboard(self) -> bool:
        text = self._system_clipboard()
        if not text:
            return False
        prompt = self.query_one("#prompt", Composer)
        prompt.focus()
        prompt.insert(text)
        return True

    def on_mouse_up(self, event: events.MouseUp) -> None:
        # Right-click paste is terminal-dependent; implement it when the
        # terminal forwards button 3 to the app.
        if event.button != 3:
            return
        try:
            prompt = self.query_one("#prompt", Composer)
            if prompt.region.contains(event.screen_x, event.screen_y):
                self._paste_system_clipboard()
                event.stop()
        except Exception:
            pass

    async def action_toggle_tools(self) -> None:
        cards = list(self.query(ToolCard))
        if not cards:
            await self._add_notice("No tool calls yet.")
            return
        if not self.show_tools:
            self.show_tools = True
            for card in cards:
                card.display = True
            expand = True
        else:
            expand = any(card._collapse.collapsed for card in cards)  # type: ignore[attr-defined]
        for card in cards:
            card._collapse.collapsed = not expand  # type: ignore[attr-defined]
        await self._add_notice("Tool output expanded." if expand else "Tool output collapsed.")

    async def _toggle_tool_visibility(self) -> None:
        self.show_tools = not self.show_tools
        for card in self.query(ToolCard):
            card.display = self.show_tools
        await self._add_notice(f"Tool cards {'shown' if self.show_tools else 'hidden'}.")

    async def action_toggle_thinking(self) -> None:
        self.show_thinking = not self.show_thinking
        for widget in self.query(".msg-thinking"):
            widget.display = self.show_thinking
        for widget in self.query(".thinking-label"):
            widget.display = self.show_thinking
        await self._add_notice(f"Thinking {'shown' if self.show_thinking else 'hidden'}.")


def run_tui(project: Optional[str] = None, session: str = "", model: str = "") -> int:
    if not os.isatty(0) or not os.isatty(1):
        print("aacode tui requires an interactive terminal (TTY).", file=sys.stderr)
        return 2
    project_path = Path(project or os.getcwd()).absolute()
    # A stale project .env must not shadow a key already configured in the
    # YAML, but it is still a valid source when the YAML has no key. Explicit
    # shell variables always win because they are already in os.environ.
    skip_llm_env: set[str] = set()
    try:
        from aacode.config import settings as _settings
        if _settings.model.api_key:
            skip_llm_env = {"LLM_API_KEY", "LLM_API_URL", "LLM_MODEL_NAME", "LLM_GATEWAY"}
    except Exception:
        pass
    load_env_files(project_path, skip_keys=skip_llm_env)
    app = TuiApp(project_path, session=session, model=model)
    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"AACode TUI could not start: {exc}", file=sys.stderr)
        return 2
    finally:
        app.worker.cancel()
