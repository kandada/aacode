# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

from __future__ import annotations

# 隐式 Diff 钩子
# tools/diff_hook.py
"""
在 run_shell 执行前后透明地检测文件变更，并附加 diff 反馈。
不增加新工具，模型完全无感知。

文件发现（混合双层）：
  策略A — 宽松命令解析（为主，<1ms，宁滥勿缺）
  策略B — 文件系统扫描（兜底，仅当策略A无结果且关注集合为空时触发）

反馈分级：
  ≤10 行变更 → diff（字符串，多 hunk 以 "..." 分隔）
  >10 行     → diff_preview（数组，每元素为 "<上下文行>\n<变更首行>"）
  多文件按变更行数升序排列，超限截断+聚合摘要
"""

import difflib
import fnmatch
import os
import re
import shlex
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class DiffHook:
    """透明的文件变更感知钩子"""

    # 策略A：匹配 -c 字符串和 heredoc 体内的文件路径
    _STRING_PATH_PATTERN = re.compile(
        r'''["']([^"']*\.(?:py|js|ts|jsx|tsx|go|rs|java|c|cpp|h|hpp|yaml|yml|json|toml|md|txt|sh|html|css|scss|less))["']''',
        re.IGNORECASE,
    )

    # 提取函数名/类名/常量
    _SYMBOL_PATTERN = re.compile(
        r'(?:def|class|async\s+def)\s+(\w+)|'
        r'(?:const|let|var|function)\s+(\w+)|'
        r'\b([A-Z][A-Z_0-9]{2,})\b'
    )

    _MAX_SNAPSHOT_CONTENT_BYTES = 1 * 1024 * 1024  # 1 MiB
    _SHELL_OPERATORS = frozenset({"|", ">", ">>", "<", "&&", "||", ";", "&"})

    def __init__(self, config, project_path: Path):
        self._config = config
        self._project_path = project_path
        self._watched_files: OrderedDict[str, None] = OrderedDict()
        self._snapshot: Dict[str, Tuple[float, int, str]] = {}
        self._is_git_repo: Optional[bool] = None
        self._gitignore_patterns: Optional[List[Tuple[str, str]]] = None

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    # ═══════════════════════════════════════════════════════════
    # pre / post — 主流程
    # ═══════════════════════════════════════════════════════════

    def pre_exec(self, command: str):
        """命令执行前：策略A 解析路径 → 必要时策略B 扫描 → 快照"""
        if not self.enabled:
            return
        paths_a = self._extract_filepaths(command)
        for p in paths_a:
            self._watch(p)
        if not paths_a and not self._watched_files:
            paths_b = self._scan_project()
            for p in paths_b:
                self._watch(p)
        self._snapshot = self._take_snapshot()

    def post_exec(self) -> Dict:
        """
        命令执行后：仅对快照中的文件 re-stat → 检测变更 → 分级生成反馈。
        返回 _changes dict 或空 dict。
        """
        if not self.enabled or not self._snapshot:
            return {}
        changed = self._detect_changes()
        if not changed:
            return {}
        return self._classify_and_format(changed)

    # ═══════════════════════════════════════════════════════════
    # 策略A：宽松命令解析
    # ═══════════════════════════════════════════════════════════

    def _extract_filepaths(self, command: str) -> List[str]:
        """宽松匹配：不限命令类型，对命令中所有 token 尝试解析为文件路径。宁滥勿缺。"""
        if not command:
            return []
        tokens = self._safe_split(command)
        paths: List[str] = []
        heredoc_body = self._extract_heredoc_body(command)

        i = 0
        while i < len(tokens):
            tok = tokens[i]

            # — 重定向目标：> / >> 后的 token —
            if tok in (">", ">>") and i + 1 < len(tokens):
                candidate = self._resolve_path(tokens[i + 1])
                if candidate and os.path.isfile(candidate):
                    paths.append(candidate)
                i += 2
                continue

            # — -c "..." 字符串体 —
            if tok == "-c" and i + 1 < len(tokens):
                body = tokens[i + 1].strip("\"'")
                for m in self._STRING_PATH_PATTERN.finditer(body):
                    candidate = self._resolve_path(m.group(1))
                    if candidate and candidate not in paths:
                        paths.append(candidate)
                i += 2
                continue

            # — heredoc 体 —
            if tok.startswith("<<") and heredoc_body:
                for m in self._STRING_PATH_PATTERN.finditer(heredoc_body):
                    candidate = self._resolve_path(m.group(1))
                    if candidate and candidate not in paths:
                        paths.append(candidate)

            # — 跳过选项和操作符 —
            if tok.startswith("-") or tok in self._SHELL_OPERATORS:
                i += 1
                continue

            # — 任意 token → 尝试解析为路径 —
            candidate = self._resolve_path(tok)
            if candidate and os.path.isfile(candidate) and candidate not in paths:
                paths.append(candidate)

            i += 1

        return paths

    # ═══════════════════════════════════════════════════════════
    # 策略B：文件系统扫描（兜底）
    # ═══════════════════════════════════════════════════════════

    def _scan_project(self) -> List[str]:
        """四层过滤扫描项目源码文件，5000 硬上限。"""
        paths: List[str] = []
        ignore_dirs = set(self._config.fs_ignore_dirs)
        extensions = set(self._config.watched_extensions)
        entry_threshold = self._config.fs_scan_dir_entry_threshold
        max_files = self._config.fs_scan_max_files
        gitignore = self._load_gitignore()

        try:
            for dirpath, dirnames, filenames in os.walk(str(self._project_path)):
                # 第1层：目录黑名单
                dirnames[:] = [
                    d for d in dirnames
                    if d not in ignore_dirs and not d.startswith(".")
                ]

                # 第2层：条目数阈值（自适应剪枝）
                dirnames[:] = [
                    d for d in dirnames
                    if self._dir_entry_count(os.path.join(dirpath, d)) <= entry_threshold
                ]

                # 第3层：.gitignore
                if gitignore:
                    dirnames[:] = [
                        d for d in dirnames
                        if not self._is_gitignored(os.path.join(dirpath, d), gitignore)
                    ]

                for fn in filenames:
                    # 第4层：扩展名白名单
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in extensions:
                        continue
                    fp = os.path.join(dirpath, fn)
                    if gitignore and self._is_gitignored(fp, gitignore):
                        continue
                    try:
                        if os.path.isfile(fp):
                            paths.append(fp)
                    except OSError:
                        pass
                    if len(paths) >= max_files:
                        return paths

        except Exception:
            pass
        return paths

    # ═══════════════════════════════════════════════════════════
    # 变更检测与分级反馈
    # ═══════════════════════════════════════════════════════════

    def _classify_and_format(
        self, changed: List[Tuple[str, Tuple[float, float]]]
    ) -> Dict:
        """按变更行数升序排列 → 两档生成反馈 → 截断 + 聚合摘要"""
        scored = []
        for filepath, _ in changed:
            diff_lines = self._count_diff_lines(filepath)
            scored.append((diff_lines, filepath))
        scored.sort(key=lambda x: x[0])

        results = []
        total_lines = 0
        truncated_files: List[str] = []
        truncated_symbols: Set[str] = set()

        for diff_lines, filepath in scored:
            if total_lines > self._config.max_total_changes_lines:
                truncated_files.append(os.path.basename(filepath))
                truncated_symbols.update(self._extract_diff_symbols_entry(filepath))
                continue

            entry: Dict = {"file": filepath}
            if diff_lines <= self._config.small_change_threshold:
                diff_text = self._compute_content_diff(filepath, diff_lines)
                if diff_text:
                    entry["diff"] = diff_text
                    total_lines += len(diff_text.split("\n"))
            else:
                preview = self._compute_diff_preview(filepath)
                if preview:
                    entry["diff_preview"] = preview
                    total_lines += len(preview)

            results.append(entry)

        output: Dict = {"total_files": len(results) + len(truncated_files), "changes": results}

        if truncated_files:
            output["truncated"] = {
                "count": len(truncated_files),
                "files": truncated_files[:3],
                "symbols": sorted(truncated_symbols)[:10],
            }

        return output

    # ═══════════════════════════════════════════════════════════
    # 关注文件集合
    # ═══════════════════════════════════════════════════════════

    def _watch(self, filepath: str):
        if not filepath.startswith(str(self._project_path)):
            return
        if not self._is_text_file(filepath):
            return
        if filepath in self._watched_files:
            del self._watched_files[filepath]
        self._watched_files[filepath] = None
        while len(self._watched_files) > self._config.max_tracked_files:
            self._watched_files.popitem(last=False)

    def _take_snapshot(self) -> Dict[str, Tuple[float, int, str]]:
        snap = {}
        for fp in self._watched_files:
            try:
                st = os.stat(fp)
                if st.st_size > self._MAX_SNAPSHOT_CONTENT_BYTES:
                    content = ""
                else:
                    content = Path(fp).read_text(encoding="utf-8", errors="replace")
                snap[fp] = (st.st_mtime, st.st_size, content)
            except OSError:
                pass
        return snap

    def _detect_changes(self) -> List[Tuple[str, Tuple[float, float]]]:
        changed = []
        for fp, (old_mtime, old_size, _) in self._snapshot.items():
            try:
                st = os.stat(fp)
                if st.st_mtime != old_mtime or st.st_size != old_size:
                    changed.append((fp, (old_mtime, st.st_mtime)))
            except OSError:
                pass
        return changed

    # ═══════════════════════════════════════════════════════════
    # Diff 生成
    # ═══════════════════════════════════════════════════════════

    def _measure_diff(self, before_text: str, current_text: str) -> Tuple[int, int, int, int]:
        """统一 diff 测量：一次 unified_diff 生成，返回 (total_changed, added, deleted, hunks)。"""
        if not before_text and not current_text:
            return 0, 0, 0, 0
        before_lines = before_text.splitlines(keepends=True)
        after_lines = current_text.splitlines(keepends=True)
        try:
            udiff = list(difflib.unified_diff(before_lines, after_lines, fromfile="", tofile="", n=2))
        except Exception:
            return 0, 0, 0, 0
        added = 0
        deleted = 0
        hunks = 0
        for line in udiff[2:]:
            if line.startswith("@@"):
                hunks += 1
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1
        return added + deleted, added, deleted, hunks

    def _compute_content_diff(self, filepath: str, estimated_lines: int) -> Optional[str]:
        if estimated_lines > self._config.max_diff_lines:
            return None
        entry = self._snapshot.get(filepath)
        if entry is None:
            return None
        before_text = entry[2]
        if not before_text:
            return None
        try:
            current = Path(filepath).read_text(encoding="utf-8", errors="replace")
            if before_text == current:
                return None
        except Exception:
            return None
        try:
            before_lines = before_text.splitlines(keepends=True)
            after_lines = current.splitlines(keepends=True)
            udiff = list(difflib.unified_diff(before_lines, after_lines, fromfile="", tofile="", n=2))
            lines_out = []
            for line in udiff[2:]:
                if line.startswith("@@"):
                    lines_out.append("  ...")
                    continue
                lines_out.append(line.rstrip("\n"))
            if len(lines_out) > self._config.max_diff_lines:
                lines_out = lines_out[:self._config.max_diff_lines]
                lines_out.append(f"  ... [截断，共 {len(udiff) - 2} 行 diff]")
            return "\n".join(lines_out)
        except Exception:
            return None

    def _compute_diff_preview(self, filepath: str) -> Optional[List[str]]:
        """生成 diff_preview 数组：每个 hunk 的 <上一行上下文>\n<变更首行>。"""
        entry = self._snapshot.get(filepath)
        if entry is None:
            return None
        before_text = entry[2]
        if not before_text:
            return None
        try:
            current = Path(filepath).read_text(encoding="utf-8", errors="replace")
            if before_text == current:
                return None
        except Exception:
            return None
        try:
            before_lines = before_text.splitlines(keepends=True)
            after_lines = current.splitlines(keepends=True)
            udiff = list(difflib.unified_diff(before_lines, after_lines, n=2))
            preview: List[str] = []
            prev_line = None
            for line in udiff[2:]:
                if len(preview) >= 5:
                    preview.append("  ...")
                    break
                if line.startswith("@@"):
                    prev_line = None
                    continue
                prefix = line[:1]
                content = line[1:].rstrip("\n")
                if prefix == " ":
                    prev_line = content
                elif prefix in ("+", "-"):
                    if prev_line is not None:
                        preview.append(f"  {prev_line}\n{prefix}{content}")
                    else:
                        preview.append(f"  \n{prefix}{content}")
            return preview if preview else None
        except Exception:
            return None

    def _count_diff_lines(self, filepath: str) -> int:
        """返回变更总行数。"""
        entry = self._snapshot.get(filepath)
        if entry is None:
            return 0
        before_text = entry[2]
        if not before_text:
            return 0
        try:
            current = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0
        if before_text == current:
            return 0
        total, _, _, _ = self._measure_diff(before_text, current)
        return total

    def _extract_diff_symbols_entry(self, filepath: str) -> Set[str]:
        """从 diff 变更行提取符号（用于 truncated 聚合）。"""
        entry = self._snapshot.get(filepath)
        if entry is None:
            return set()
        before_text = entry[2]
        if not before_text:
            return set()
        try:
            current = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return set()
        return self._extract_diff_symbols(before_text, current)

    def _extract_diff_symbols(self, before_text: str, current_text: str) -> Set[str]:
        """从 unified diff 的变更行中提取符号。"""
        symbols = set()
        try:
            before_lines = before_text.splitlines(keepends=True)
            after_lines = current_text.splitlines(keepends=True)
            udiff = list(difflib.unified_diff(before_lines, after_lines, fromfile="", tofile="", n=2))
            for line in udiff[2:]:
                prefix = line[:1]
                if prefix in ("+", "-") and not line.startswith(("+++", "---", "@@")):
                    symbols.update(self._extract_symbols(line[1:]))
        except Exception:
            pass
        return symbols

    # ═══════════════════════════════════════════════════════════
    # 命令解析辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _safe_split(command: str) -> List[str]:
        try:
            return shlex.split(command)
        except ValueError:
            return command.split()

    def _resolve_path(self, token: str) -> Optional[str]:
        token = token.strip("\"'")
        if token.startswith("~"):
            token = os.path.expanduser(token)
        candidate = os.path.join(self._project_path, token) if not os.path.isabs(token) else token
        candidate = os.path.normpath(candidate)
        if candidate.startswith(str(self._project_path)):
            return candidate
        return None

    def _extract_heredoc_body(self, command: str) -> Optional[str]:
        """提取 heredoc 体：<< 到结束标记之间。"""
        m = re.search(r'<<\s*["\']?(\w+)["\']?', command)
        if not m:
            return None
        marker = m.group(1)
        start = m.end()
        rest = command[start:]
        idx = rest.find(marker)
        if idx == -1:
            return None
        return rest[:idx]

    # ═══════════════════════════════════════════════════════════
    # 文件系统扫描辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _dir_entry_count(dirpath: str) -> int:
        try:
            return len(os.listdir(dirpath))
        except OSError:
            return 0

    def _load_gitignore(self) -> Optional[List[Tuple[str, str]]]:
        if self._gitignore_patterns is not None:
            return self._gitignore_patterns
        gi = self._project_path / ".gitignore"
        if not gi.exists():
            self._gitignore_patterns = []
            return self._gitignore_patterns
        try:
            patterns = []
            gi_dir = str(self._project_path)
            for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append((gi_dir, line))
            self._gitignore_patterns = patterns
        except Exception:
            self._gitignore_patterns = []
        return self._gitignore_patterns

    @staticmethod
    def _is_gitignored(filepath: str, gitignore_patterns: List[Tuple[str, str]]) -> bool:
        for base_dir, pattern in gitignore_patterns:
            if pattern.endswith("/"):
                pattern = pattern.rstrip("/")
                if fnmatch.fnmatch(os.path.basename(filepath), pattern):
                    return True
            else:
                name = os.path.basename(filepath)
                if fnmatch.fnmatch(name, pattern):
                    return True
        return False

    # ═══════════════════════════════════════════════════════════
    # 符号提取 & 文件类型判断
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _extract_symbols(cls, text: str) -> Set[str]:
        symbols = set()
        for m in cls._SYMBOL_PATTERN.finditer(text):
            symbol = m.group(1) or m.group(2) or m.group(3)
            if symbol:
                symbols.add(symbol)
        return symbols

    def _is_text_file(self, filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        if ext:
            return ext in self._config.watched_extensions
        if not os.path.isfile(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
            return b"\x00" not in chunk
        except Exception:
            return False
