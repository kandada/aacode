from __future__ import annotations

# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# tools/browser_tools.py
"""
浏览器 + 无障碍（Accessibility）工具，后端为 fastbrowser 内核。

设计要点（对齐 aacode-rs 的 tools/browser.rs）：
- 惰性初始化：首次使用时才启动内核，探测一次 Chromium 后缓存「可用性」。
- 浏览器工具（fetch_rendered / browser_call / browser_tools）依赖真实 Chromium；
  ax_act 的「桌面原生 AX」不依赖 Chromium（走 macOS AXUIElement / Windows UIA /
  Linux AT-SPI），只有「web 表面」那条路才走浏览器引擎。
- 工具刻意少而通用：长尾能力经 browser_call + browser_tools 渐进发现，不把
  fastbrowser 的 100+ 工具塞进 prompt。
"""

import asyncio
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fastbrowser as _fb
except Exception:  # 无对应平台 wheel（musl / PyPy 等）时优雅降级
    _fb = None

# 浏览器引擎真实可用的判定（非 mock 即真实 Chromium）。
_REAL_ENGINES = ("bundled", "chromium")


def _tool_cfg() -> Any:
    """懒加载 tools 配置（避免模块导入期构造 Settings）。"""
    try:
        if __package__ in (None, ""):
            from config import settings
        else:
            from ..config import settings
        return getattr(settings, "tools", None)
    except Exception:
        return None


class FastbrowserTools:
    """fastbrowser 内核的 aacode 工具封装（浏览器 + 无障碍）。"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._browser = None
        self._probed = False  # 是否已完成一次性探测
        self._real_engine = False  # 是否为真实浏览器引擎（非 mock）
        self._init_error = ""  # 初始化失败原因
        self._lock = asyncio.Lock()  # 串行化引擎访问（防同轮并发竞争）

    # ── 后端探测 / 装配 ────────────────────────────────────────────────

    def _find_chrome(self) -> Optional[str]:
        """定位 Chromium 可执行文件：CHROME_PATH env → 配置 → 系统常见路径。"""
        env = os.getenv("CHROME_PATH")
        if env and os.path.exists(env):
            return env
        cfg = _tool_cfg()
        cp = getattr(cfg, "chrome_path", None) if cfg else None
        if cp and os.path.exists(cp):
            return cp

        candidates: List[str] = []
        if sys.platform == "darwin":
            candidates = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ]
        elif sys.platform.startswith("linux"):
            for name in (
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
                "microsoft-edge",
            ):
                p = shutil.which(name)
                if p:
                    candidates.append(p)
        elif sys.platform == "win32":
            bases = [
                os.getenv("PROGRAMFILES", r"C:\Program Files"),
                os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                os.getenv("LOCALAPPDATA", ""),
            ]
            for base in bases:
                if not base:
                    continue
                candidates += [
                    os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(
                        base, "Microsoft", "Edge", "Application", "msedge.exe"
                    ),
                    os.path.join(base, "Chromium", "Application", "chrome.exe"),
                ]
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    def _build_config(
        self, chrome: Optional[str], cdp_url: Optional[str]
    ) -> Dict[str, Any]:
        cfg = _tool_cfg()
        headless = getattr(cfg, "browser_headless", True) if cfg else True
        vw = getattr(cfg, "browser_viewport_width", 1280) if cfg else 1280
        vh = getattr(cfg, "browser_viewport_height", 800) if cfg else 800

        engine = "chromium" if cdp_url else ("bundled" if chrome else "mock")
        conf: Dict[str, Any] = {
            "engine": engine,
            "rendering_mode": "headless" if headless else "hosted",
            "viewport": {"width": vw, "height": vh, "device_scale_factor": 1.0},
            "surface": {"enabled": True, "provider": "auto", "prefer_ax_tree": True},
            "command_timeout_ms": 30000,
        }
        if cdp_url:
            conf["cdp_url"] = cdp_url
        return conf

    async def _ensure_backend(self):
        """一次性探测 + 初始化。返回内核句柄；不可用则 None 并记录原因。"""
        if self._probed:
            return self._browser
        async with self._lock:
            if self._probed:
                return self._browser
            self._probed = True

            if _fb is None:
                self._init_error = (
                    "fastbrowser package not installed in this Python"
                    f" ({sys.executable}); run: {sys.executable} -m pip install fastbrowser"
                )
                return None

            cdp_url = getattr(_tool_cfg(), "cdp_url", None) if _tool_cfg() else None
            chrome = None if cdp_url else self._find_chrome()
            if chrome:
                os.environ.setdefault("CHROME_PATH", chrome)

            # 无 Chromium 仍可装配 surface 层（桌面原生 AX 可用，web 表面退化为 mock）。
            if chrome is None and cdp_url is None:
                self._init_error = (
                    "no Chromium found; install Chrome / Chromium, or set CHROME_PATH"
                    " (or cdp_url to attach an existing Chrome)"
                )

            try:
                b = _fb.AsyncFastBrowser()
                await b.init(self._build_config(chrome, cdp_url))
                self._browser = b
                info = b.get_info() if hasattr(b, "get_info") else {}
                engine = str(info.get("engine", "") or "")
                self._real_engine = engine in _REAL_ENGINES
                return b
            except Exception as e:
                self._init_error = f"fastbrowser init failed: {e}"
                return None

    def _unavailable(self) -> Dict[str, Any]:
        hint = (
            "Fix the cause in `detail` (install the missing package / Chrome, or set"
            " CHROME_PATH). No-backend fallbacks: `fetch_url` (static pages) or"
            " `run_skills('playwright', {...})` (JS pages / screenshots)."
            " Note: ax_act on *native desktop apps* does not need Chromium, but it"
            " still needs the fastbrowser package."
        )
        return {
            "success": False,
            "error": "browser backend unavailable",
            "detail": self._init_error or "unknown",
            "hint": hint,
        }

    def _require_real_engine(self, b) -> Optional[Dict[str, Any]]:
        """浏览器工具专用：非真实引擎（无 Chromium）时返回降级错误。"""
        if b is None:
            return self._unavailable()
        if not self._real_engine:
            return {
                "success": False,
                "error": "browser backend unavailable (no real Chromium)",
                "detail": self._init_error
                or "engine fell back to mock (no Chromium found)",
                "hint": self._unavailable()["hint"],
            }
        return None

    async def cleanup(self):
        """释放内核（关闭 Chrome 子进程）。"""
        if self._browser is not None:
            try:
                self._browser.shutdown()
            except Exception:
                pass
            self._browser = None

    # ── 结果清理 / 归档 ────────────────────────────────────────────────

    @staticmethod
    def _clean_html(html: str) -> str:
        html = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<head[^>]*>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _dominant_text(self, result: Dict[str, Any]) -> Optional[str]:
        if isinstance(result.get("html"), str):
            return self._clean_html(result["html"])
        for key in ("text", "content", "markdown", "value"):
            if isinstance(result.get(key), str) and result[key].strip():
                return result[key]
        return None

    def _compact(
        self, result: Dict[str, Any], tool: str, max_chars: int
    ) -> Dict[str, Any]:
        limit = max_chars if max_chars > 0 else 6000
        body = self._dominant_text(result)
        if body is None:
            import json

            body = json.dumps(result, ensure_ascii=False)
        total = len(body)
        preview = body if total <= limit else body[:limit]
        out: Dict[str, Any] = {
            "success": True,
            "result": preview,
            "truncated": total > limit,
            "chars": total,
        }
        if total > limit:
            extracts = self.project_path / ".aacode" / "extracts"
            extracts.mkdir(parents=True, exist_ok=True)
            path = extracts / f"browser_{tool}_{uuid.uuid4().hex[:8]}.txt"
            path.write_text(body, encoding="utf-8")
            out["archive"] = {"path": str(path), "chars": total}
            out["hint"] = (
                f"Full result ({total} chars) saved to {path}. Explore it with"
                " run_shell (grep/head/tail) instead of cat-ing it into context."
            )
        return out

    # ── 工具实现 ───────────────────────────────────────────────────────

    async def fetch_rendered(
        self,
        url: str,
        max_chars: int = 5000,
        **kwargs,
    ) -> Dict[str, Any]:
        """真浏览器渲染 JS 后取文本（fetch_url 的 SPA/JS 页面补位）。"""
        if not url:
            return {"success": False, "error": "empty url"}
        b = await self._ensure_backend()
        err = self._require_real_engine(b)
        if err:
            return err

        async with self._lock:
            try:
                opened = await b.open(url)
                tab = opened.get("tab", 0)
                # Best-effort settle for SPA hydration; never fatal if unsupported.
                for state in ("networkidle", "load"):
                    try:
                        await b.tool_call(
                            "wait_for_load_state",
                            {"tab": tab, "state": state, "timeout_ms": 8000},
                        )
                    except Exception:
                        pass
                text = ""
                for _ in range(12):
                    await asyncio.sleep(0.3)
                    tv = await b.tool_call(
                        "extract_text", {"tab": tab, "max_chars": max_chars}
                    )
                    text = (tv.get("text") or "").strip()
                    if text:
                        break
                title = (await b.tool_call("get_page_title", {"tab": tab})).get(
                    "title", ""
                )
                try:
                    await b.tool_call("close_tab", {"tab": tab})
                except Exception:
                    pass
            except Exception as e:
                return {"success": False, "error": f"fetch_rendered failed: {e}"}

        if not text:
            return {
                "success": False,
                "url": url,
                "title": title,
                "error": "no readable content (page may be JS-only, empty, or blocked)",
                "hint": "Use browser_call (e.g. navigate then interact) or fall back to fetch_url.",
            }
        return {
            "success": True,
            "url": url,
            "title": title,
            "content": text[:max_chars],
            "content_length": len(text),
        }

    async def browser_tools(
        self,
        mode: str = "names",
        name: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """渐进发现 fastbrowser 工具：names / compact / full / help(name)。"""
        b = await self._ensure_backend()
        err = self._require_real_engine(b)
        if err:
            return err

        try:
            tools = b.tool_list()
        except Exception as e:
            return {"success": False, "error": f"tool_list failed: {e}"}
        if isinstance(tools, dict):
            tools = tools.get("tools", [])
        tools = tools or []

        if mode == "help":
            if not name:
                return {"success": False, "error": "mode='help' requires `name`"}
            for t in tools:
                if t.get("name") == name:
                    return {"success": True, "mode": "help", "tool": t}
            return {"success": False, "error": f"unknown browser tool '{name}'"}

        def short_desc(s: str) -> str:
            line = (s or "").strip().splitlines()
            line = line[0] if line else ""
            return line[:80] + ("…" if len(line) > 80 else "")

        if mode == "compact":
            out = [
                {
                    "name": t.get("name"),
                    "description": short_desc(t.get("description", "")),
                    "params": list((t.get("params") or {}).keys()),
                    "required": [
                        k
                        for k, v in (t.get("params") or {}).items()
                        if v.get("required")
                    ],
                }
                for t in tools
            ]
        elif mode == "full":
            out = [
                {
                    "name": t.get("name"),
                    "description": short_desc(t.get("description", "")),
                    "params": t.get("params", {}),
                }
                for t in tools
            ]
        else:
            out = [t.get("name") for t in tools]

        return {"success": True, "mode": mode, "count": len(tools), "tools": out}

    async def browser_call(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        compact: bool = False,
        max_chars: int = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        """按名调任意 fastbrowser 工具（含全部 ax_*）。"""
        if not name:
            return {"success": False, "error": "empty tool name"}
        b = await self._ensure_backend()
        err = self._require_real_engine(b)
        if err:
            return err

        params = dict(args or {})
        async with self._lock:
            try:
                result = await b.tool_call(name, params)
            except Exception as e:
                return {"success": False, "error": f"browser_call '{name}' failed: {e}"}

        # 内层工具“返回”失败（如 download 的 {ok:false,status:403}）时，
        # 不要外层仍报 success:true，否则模型会误以为成功。
        failure = self._inner_failure(result)
        if failure:
            return {
                "success": False,
                "error": f"{name} failed: {failure}",
                "tool": name,
                "result": result,
            }

        if compact:
            return self._compact(result, name, max_chars)
        import json

        if len(json.dumps(result, ensure_ascii=False)) > 24000:
            out = self._compact(result, name, max_chars)
            out["compacted"] = True
            return out
        return {"success": True, "result": result}

    @staticmethod
    def _inner_failure(result: Any) -> Optional[str]:
        """识别 fastbrowser 工具“返回型”失败，返回原因文本或 None。"""
        if not isinstance(result, dict):
            return None
        if result.get("ok") is False:
            status = result.get("status")
            return "ok=false" + (f" (status {status})" if status else "")
        if result.get("success") is False:
            return str(
                result.get("error") or result.get("message") or "reported failure"
            )
        if result.get("error"):
            return str(result["error"])
        return None

    async def ax_act(
        self,
        action: str,
        ref: Optional[str] = None,
        target: Optional[str] = None,
        text: Optional[str] = None,
        value: Optional[str] = None,
        key: Optional[str] = None,
        dx: Optional[float] = None,
        dy: Optional[float] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """无障碍（AX）感知 + 动作。action='snapshot' 返回无障碍树，其余施加动作。"""
        if not action:
            return {"success": False, "error": "missing action"}
        b = await self._ensure_backend()
        if b is None:
            return self._unavailable()

        async with self._lock:
            try:
                if action == "snapshot":
                    params: Dict[str, Any] = {}
                    if target:
                        params["target"] = target
                    return await b.tool_call("ax_snapshot", params)
                params = {"action": action}
                if ref is not None:
                    params["ref"] = ref
                if target:
                    params["target"] = target
                if text is not None:
                    params["text"] = text
                if value is not None:
                    params["value"] = value
                if key is not None:
                    params["key"] = key
                if dx is not None:
                    params["dx"] = dx
                if dy is not None:
                    params["dy"] = dy
                if x is not None:
                    params["x"] = x
                if y is not None:
                    params["y"] = y
                return await b.tool_call("ax_act", params)
            except Exception as e:
                return {"success": False, "error": f"ax_act '{action}' failed: {e}"}
