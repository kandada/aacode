# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# 原子工具 - 简化版
# tools/atomic_tools.py
"""
轻量级原子工具
遵循"bash是万能适配器"原则,简化实现
仅保留 run_shell，文件操作通过 shell 命令完成
"""

import asyncio
import collections
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from aacode.i18n import t


def _no_window_kwargs() -> dict:
    """Windows 下隐藏子进程控制台窗口（避免 cmd.exe 弹窗闪烁），其他平台无操作"""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def _smart_decode(data: bytes) -> str:
    """Decode bytes to string, trying UTF-8 first then GBK on Windows."""
    if os.name != "nt":
        return data.decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


DEFAULT_MAX_OUTPUT_CHARS = 20000
DEFAULT_MAX_OUTPUT_LINES = 500


def _is_unlimited(val) -> bool:
    """Check if a value means 'no limit'."""
    if val is None or val == 0:
        return True
    if isinstance(val, str) and val.lower() in ('none', 'null', '', 'full'):
        return True
    return False


class AtomicTools:
    """简化的原子工具集"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self._background_processes: Dict[str, dict] = {}
        try:
            if __package__ in (None, ""):
                from config import settings
            else:
                from ..config import settings
            from .diff_hook import DiffHook
            self._diff_hook = DiffHook(settings.diff_hook, project_path)
        except Exception:
            self._diff_hook = None

    async def run_shell(
        self, command: str = None, timeout: Optional[int] = None, stdin_input: str = None,
        max_output: Any = None, stop_on_exit: bool = False,
        action: str = "exec", process_id: str = None,
        max_lines: int = None, idle_timeout: int = None,
        use_pty: bool = False, max_output_lines: int = None,
        full_output: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """
        执行shell命令(带安全护栏)

        Args:
            command: 要执行的shell命令
            timeout: 超时时间（秒）
            stdin_input: 传给程序的标准输入内容（可选）
            max_output: 限制返回的输出最大字符数
            stop_on_exit: 主进程退出后是否不等子进程管道立即返回
            action: 操作模式 - "exec", "spawn", "check", "read", "write", "kill", "jobs"
            process_id: spawn 返回的进程ID，用于 check/read/write/kill
            max_lines: 环形缓冲区行数限制
            idle_timeout: 空闲超时（秒），无输出超过此时长则 kill
            full_output: True 时禁用默认 20k/500 行输出上限
            max_output_lines: 默认输出行数上限（500）
            use_pty: 是否使用伪终端（仅 Linux/macOS）

        Note: **kwargs 用于接收并忽略模型可能传入的额外参数
        """
        # Cache-safe output budget: the capped content is what enters context
        # from the start, and the full output is archived for later inspection.
        wants_full = (
            full_output
            or (isinstance(max_output, str) and max_output.lower() == "full")
            or (max_output is not None and _is_unlimited(max_output))
        )
        if wants_full:
            max_output = None
            max_output_lines = None
        else:
            if max_output is None:
                max_output = DEFAULT_MAX_OUTPUT_CHARS
            if max_output_lines is None:
                max_output_lines = DEFAULT_MAX_OUTPUT_LINES

        try:
            if timeout is None:
                if __package__ in (None, ""):
                    from config import settings
                else:
                    from ..config import settings
                timeout = settings.timeouts.shell_command

            if action == "exec":
                return await self._exec_action(command, timeout, stdin_input,
                                               max_output, stop_on_exit,
                                               max_lines, idle_timeout, use_pty,
                                               max_output_lines)
            elif action == "spawn":
                return await self._spawn_action(command, max_lines,
                                                idle_timeout, use_pty)
            elif action == "check":
                return self._check_action(process_id)
            elif action == "read":
                return self._read_action(process_id, max_lines)
            elif action == "write":
                return await self._write_action(process_id, stdin_input)
            elif action == "kill":
                return await self._kill_action(process_id)
            elif action == "jobs":
                return self.list_jobs()
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"Tool execution exception: {error_type}: {str(e)}"
            print(f"\u274c {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "command": command,
                "working_directory": str(self.project_path),
            }

    # ─── action: exec ───────────────────────────────────────────

    async def _exec_action(self, command, timeout, stdin_input, max_output,
                           stop_on_exit, max_lines, idle_timeout, use_pty,
                           max_output_lines=None):
        """同步执行命令（原有行为 + max_lines/idle_timeout/use_pty 增强）"""
        if not command:
            return {"success": False, "error": "command is required for action=\"exec\""}

        safety_check = self.safety_guard.check_command(command)
        if not safety_check["allowed"]:
            return {
                "error": f"Command rejected by safety guard: {safety_check['reason']}",
                "allowed": False,
                "command": command,
            }

        print(f"\U0001f527 Executing command: {command}")

        if self._diff_hook:
            self._diff_hook.pre_exec(command)

        pty_info = None
        if use_pty and os.name != "nt":
            pty_info = self._create_pty()
            if pty_info is None:
                print("\u26a0\ufe0f  PTY creation failed, falling back to pipe mode")
                use_pty = False

        if use_pty and pty_info:
            result = await self._exec_with_pty(command, timeout, stdin_input,
                                               max_output, max_lines,
                                               idle_timeout, pty_info,
                                               max_output_lines)
            await self._attach_changes(result)
            return result

        stdin_mode = asyncio.subprocess.PIPE if stdin_input else asyncio.subprocess.DEVNULL

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.project_path),
            stdin=stdin_mode,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            **_no_window_kwargs(),
        )

        try:
            if stdin_input:
                stdout_text, stderr_text = await self._exec_with_stdin(
                    process, stdin_input, timeout)
            else:
                stdout_text, stderr_text = await self._exec_streaming(
                    process, timeout, stop_on_exit, max_lines, idle_timeout)

            stdout_text, stdout_truncated = self._apply_max_output(
                stdout_text, max_output, "stdout", max_output_lines)
            stderr_text, stderr_truncated = self._apply_max_output(
                stderr_text, max_output, "stderr", max_output_lines)

            result = {
                "success": True,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "_max_output_setting": max_output,
                "command": command,
                "working_directory": str(self.project_path),
            }
            await self._attach_changes(result)
            return result
        except asyncio.TimeoutError:
            process.terminate()
            await self._reap_process(process, 5.0)
            result = {
                "success": True,
                "error": f"Command execution timeout ({timeout}s)",
                "timeout": True,
                "command": command,
                "working_directory": str(self.project_path),
            }
            await self._attach_changes(result)
            return result

    async def _exec_with_stdin(self, process, stdin_input, timeout):
        """执行带 stdin_input 的命令"""
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=stdin_input.encode("utf-8")),
            timeout=timeout,
        )
        return _smart_decode(stdout), _smart_decode(stderr)

    async def _exec_streaming(self, process, timeout, stop_on_exit,
                              max_lines, idle_timeout):
        """流式读取 stdout/stderr，带 idle_timeout 支持"""
        buf_cls = (lambda: collections.deque(maxlen=max_lines)) if max_lines else list
        stdout_buf = buf_cls()
        stderr_buf = buf_cls()

        stdout_reader = asyncio.create_task(
            self._stream_lines(process.stdout, "\u2502 ", stdout_buf, idle_timeout, process)
        )
        stderr_reader = asyncio.create_task(
            self._stream_lines(process.stderr, "\u2570 ", stderr_buf, idle_timeout, process)
        )

        try:
            await self._poll_process_exit(process, timeout, idle_timeout, stdout_buf, stderr_buf)

            if stop_on_exit:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(stdout_reader, stderr_reader),
                        timeout=0.5,
                    )
                except asyncio.TimeoutError:
                    stdout_reader.cancel()
                    stderr_reader.cancel()
                    await asyncio.gather(stdout_reader, stderr_reader,
                                         return_exceptions=True)
            else:
                await asyncio.gather(stdout_reader, stderr_reader)
        except:
            stdout_reader.cancel()
            stderr_reader.cancel()
            await asyncio.gather(stdout_reader, stderr_reader,
                                 return_exceptions=True)
            raise

        stdout_text = "\n".join(stdout_buf)
        stderr_text = "\n".join(stderr_buf)

        return stdout_text, stderr_text

    async def _exec_with_pty(self, command, timeout, stdin_input,
                             max_output, max_lines, idle_timeout, pty_info,
                             max_output_lines=None):
        """通过 PTY 同步执行命令（stdout/stderr 合并）"""
        master_fd, slave_fd = pty_info
        cwd = str(self.project_path)
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color"}

        process = await asyncio.create_subprocess_exec(
            '/bin/sh', '-c', command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            pass_fds=(slave_fd,),
            preexec_fn=os.setsid,
            close_fds=True,
            env=env,
        )
        os.close(slave_fd)

        reader = await self._create_pty_reader(master_fd)

        if stdin_input:
            try:
                os.write(master_fd, stdin_input.encode("utf-8"))
            except Exception:
                pass

        buf_cls = (lambda: collections.deque(maxlen=max_lines)) if max_lines else list
        output_buf = buf_cls()

        reader_task = asyncio.create_task(
            self._stream_pty_reader(reader, output_buf, idle_timeout, process)
        )

        try:
            await self._poll_process_exit(process, timeout, idle_timeout,
                                          output_buf, None)
        except asyncio.TimeoutError:
            process.terminate()
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass
            await self._reap_process(process, 5.0)
            return {
                "success": True,
                "error": f"Command execution timeout ({timeout}s)",
                "timeout": True,
                "command": command,
                "working_directory": str(self.project_path),
            }

        try:
            await asyncio.wait_for(reader_task, timeout=0.5)
        except asyncio.TimeoutError:
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass

        if isinstance(output_buf, collections.deque):
            stdout_text = "\n".join(output_buf)
        else:
            stdout_text = "\n".join(output_buf)

        stdout_text, stdout_truncated = self._apply_max_output(
            stdout_text, max_output, "stdout", max_output_lines)

        return {
            "success": True,
            "returncode": process.returncode,
            "stdout": stdout_text,
            "stderr": "",
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": False,
            "_max_output_setting": max_output,
            "command": command,
            "working_directory": str(self.project_path),
            "pty": True,
        }

    # ─── background job persistence ─────────────────────────────

    def _jobs_dir(self) -> Path:
        return self.project_path / ".aacode" / "jobs"

    def _job_meta_path(self, job_id: str) -> Path:
        return self._jobs_dir() / f"job_{job_id}.json"

    def _job_log_path(self, job_id: str) -> Path:
        return self._jobs_dir() / f"job_{job_id}.log"

    def _write_job_meta(self, job_id: str, meta: Dict[str, Any]) -> None:
        try:
            self._jobs_dir().mkdir(parents=True, exist_ok=True)
            self._job_meta_path(job_id).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _read_job_meta(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._job_meta_path(job_id).read_text(encoding="utf-8"))
        except Exception:
            return None

    def _mark_job_stopped(self, job_id: str) -> None:
        meta = self._read_job_meta(job_id)
        if not meta:
            return
        meta["stopped_at"] = time.time()
        self._write_job_meta(job_id, meta)

    def _pid_alive(self, pid: int) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except Exception:
            return False

    def _terminate_pid(self, pid: int, grouped: bool = True) -> None:
        """Terminate a detached job; kill its process group when possible."""
        if not isinstance(pid, int) or pid <= 0:
            return
        try:
            if os.name != "nt" and grouped:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    return
                except (ProcessLookupError, PermissionError):
                    pass
                except Exception:
                    pass
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:
            pass

    def _job_summary(self, job_id: str, bg: Optional[Dict] = None) -> Dict[str, Any]:
        meta = self._read_job_meta(job_id) or {}
        if bg:
            proc = bg.get("process")
            running = proc.returncode is None if proc else False
            mode = bg.get("mode", meta.get("mode", "pipe"))
            command = bg.get("command", meta.get("command", ""))
            started_at = meta.get("started_at", bg.get("started_at"))
        else:
            pid = meta.get("pid")
            running = not meta.get("stopped_at") and self._pid_alive(pid)
            mode = meta.get("mode", "unknown")
            command = meta.get("command", "")
            started_at = meta.get("started_at")
        return {
            "job_id": job_id,
            "pid": meta.get("pid"),
            "running": running,
            "mode": mode,
            "command": command,
            "started_at": started_at,
            "log_path": meta.get("log_path"),
            "managed_in_this_process": bg is not None,
        }

    def list_jobs(self, limit: int = 20) -> Dict[str, Any]:
        """List background jobs from this process and persisted metadata."""
        limit = max(1, min(int(limit or 20), 100))
        jobs = {}
        for job_id, bg in self._background_processes.items():
            jobs[job_id] = self._job_summary(job_id, bg)

        try:
            for path in sorted(
                self._jobs_dir().glob("job_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            ):
                job_id = path.stem.removeprefix("job_")
                if job_id not in jobs:
                    jobs[job_id] = self._job_summary(job_id)
                if len(jobs) >= limit:
                    break
        except Exception:
            pass

        ordered = list(jobs.values())[:limit]
        return {"success": True, "jobs": ordered, "count": len(ordered)}

    # ─── action: spawn ──────────────────────────────────────────

    async def _spawn_action(self, command, max_lines, idle_timeout, use_pty):
        """后台启动命令，返回 process_id"""
        if not command:
            return {"success": False, "error": "command is required for action=\"spawn\""}

        safety_check = self.safety_guard.check_command(command)
        if not safety_check["allowed"]:
            return {
                "error": f"Command rejected by safety guard: {safety_check['reason']}",
                "allowed": False,
                "command": command,
            }

        pid = uuid.uuid4().hex[:12]
        print(f"\U0001f527 Spawning background process [{pid}]: {command}")
        self._jobs_dir().mkdir(parents=True, exist_ok=True)
        log_path = self._job_log_path(pid)
        log_handle = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)

        pty_info = None
        if use_pty and os.name != "nt":
            pty_info = self._create_pty()
            if pty_info is None:
                print("\u26a0\ufe0f  PTY creation failed, falling back to pipe mode")
                use_pty = False

        if use_pty and pty_info:
            return await self._spawn_with_pty(command, pid, max_lines,
                                              idle_timeout, pty_info,
                                              log_path, log_handle)

        spawn_kwargs = _no_window_kwargs()
        if os.name != "nt":
            # Isolate the job in its own process group so kill() can stop
            # child processes as well as the shell.
            spawn_kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.project_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            **spawn_kwargs,
        )

        maxlen = max_lines if max_lines else 10000
        stdout_deque = collections.deque(maxlen=maxlen)
        stderr_deque = collections.deque(maxlen=maxlen)

        async def _bg_stream_reader(stream, prefix, buf, proc):
            last_output = time.monotonic()
            while True:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=0.5)
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    if idle_timeout and time.monotonic() - last_output > idle_timeout:
                        print(f"\u23f1\ufe0f  Idle timeout [{pid}] - terminating")
                        proc.terminate()
                        break
                    continue
                if not line:
                    break
                text = _smart_decode(line).rstrip()
                buf.append(text)
                last_output = time.monotonic()
                try:
                    log_handle.write(text + "\n")
                    log_handle.flush()
                except Exception:
                    pass
                print(f"{prefix}{text}", flush=True)
                if proc.returncode is not None:
                    break

        stdout_reader = asyncio.create_task(
            _bg_stream_reader(process.stdout, "\u2502 ", stdout_deque, process)
        )
        stderr_reader = asyncio.create_task(
            _bg_stream_reader(process.stderr, "\u2570 ", stderr_deque, process)
        )

        started_epoch = time.time()
        self._background_processes[pid] = {
            "process": process,
            "stdout_deque": stdout_deque,
            "stderr_deque": stderr_deque,
            "stdout_reader": stdout_reader,
            "stderr_reader": stderr_reader,
            "command": command,
            "started_at": time.monotonic(),
            "mode": "pipe",
            "log_path": log_path,
            "log_handle": log_handle,
        }
        self._write_job_meta(
            pid,
            {
                "job_id": pid,
                "pid": process.pid,
                "command": command,
                "mode": "pipe",
                "started_at": started_epoch,
                "cwd": str(self.project_path),
                "log_path": str(log_path.relative_to(self.project_path)),
            },
        )

        recent_stdout = "\n".join(stdout_deque) if stdout_deque else ""

        return {
            "success": True,
            "process_id": pid,
            "job_id": pid,
            "initial_stdout": recent_stdout,
            "mode": "pipe",
            "command": command,
            "working_directory": str(self.project_path),
            "log_path": str(log_path.relative_to(self.project_path)),
        }

    async def _spawn_with_pty(self, command, pid, max_lines,
                              idle_timeout, pty_info, log_path, log_handle):
        """后台 PTY 模式启动"""
        master_fd, slave_fd = pty_info
        cwd = str(self.project_path)
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color"}

        process = await asyncio.create_subprocess_exec(
            '/bin/sh', '-c', command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            pass_fds=(slave_fd,),
            preexec_fn=os.setsid,
            close_fds=True,
            env=env,
        )
        os.close(slave_fd)

        reader = await self._create_pty_reader(master_fd)

        maxlen = max_lines if max_lines else 10000
        output_deque = collections.deque(maxlen=maxlen)

        async def _bg_pty_reader(reader, buf, proc, inner_pid):
            last_output = time.monotonic()
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=0.5)
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    if idle_timeout and time.monotonic() - last_output > idle_timeout:
                        print(f"\u23f1\ufe0f  Idle timeout [{inner_pid}] - terminating")
                        proc.terminate()
                        break
                    continue
                if not line:
                    break
                text = _smart_decode(line).rstrip()
                buf.append(text)
                last_output = time.monotonic()
                try:
                    log_handle.write(text + "\n")
                    log_handle.flush()
                except Exception:
                    pass
                print(f"\u2502 {text}", flush=True)
                if proc.returncode is not None:
                    break

        reader_task = asyncio.create_task(
            _bg_pty_reader(reader, output_deque, process, pid)
        )

        started_epoch = time.time()
        self._background_processes[pid] = {
            "process": process,
            "stdout_deque": output_deque,
            "stderr_deque": None,
            "stdout_reader": reader_task,
            "stderr_reader": None,
            "command": command,
            "started_at": time.monotonic(),
            "mode": "pty",
            "pty_reader": reader,
            "master_fd": master_fd,
            "log_path": log_path,
            "log_handle": log_handle,
        }
        self._write_job_meta(
            pid,
            {
                "job_id": pid,
                "pid": process.pid,
                "command": command,
                "mode": "pty",
                "started_at": started_epoch,
                "cwd": str(self.project_path),
                "log_path": str(log_path.relative_to(self.project_path)),
            },
        )

        recent_stdout = "\n".join(output_deque) if output_deque else ""

        return {
            "success": True,
            "process_id": pid,
            "job_id": pid,
            "initial_stdout": recent_stdout,
            "mode": "pty",
            "command": command,
            "working_directory": str(self.project_path),
            "log_path": str(log_path.relative_to(self.project_path)),
        }

    # ─── action: check ──────────────────────────────────────────

    def _check_action(self, process_id):
        """查询后台进程状态"""
        if not process_id:
            return {"success": False,
                    "error": "process_id is required for action=\"check\""}

        bg = self._background_processes.get(process_id)
        if not bg:
            meta = self._read_job_meta(process_id)
            if not meta or meta.get("stopped_at"):
                return {"success": False,
                        "error": f"Process not found: {process_id}"}
            return {
                "success": True,
                "process_id": process_id,
                "job_id": process_id,
                "running": self._pid_alive(meta.get("pid")),
                "returncode": None,
                "command": meta.get("command", ""),
                "mode": meta.get("mode", "unknown"),
                "log_path": meta.get("log_path"),
                "persisted": True,
            }

        proc = bg["process"]
        running = proc.returncode is None

        result = {
            "success": True,
            "process_id": process_id,
            "job_id": process_id,
            "running": running,
            "returncode": proc.returncode,
            "command": bg["command"],
            "mode": bg["mode"],
            "log_path": str(bg["log_path"].relative_to(self.project_path))
            if bg.get("log_path")
            else None,
        }
        if not running:
            self._mark_job_stopped(process_id)
            self._cleanup_process(process_id)
        return result

    # ─── action: read ───────────────────────────────────────────

    def _read_action(self, process_id, max_lines):
        """读取后台进程的输出"""
        if not process_id:
            return {"success": False,
                    "error": "process_id is required for action=\"read\""}

        bg = self._background_processes.get(process_id)
        if not bg:
            meta = self._read_job_meta(process_id)
            if not meta:
                return {"success": False,
                        "error": f"Process not found: {process_id}"}
            log_text = ""
            log_path = meta.get("log_path")
            if log_path:
                try:
                    lines = (self.project_path / log_path).read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    if max_lines:
                        lines = lines[-max_lines:]
                    log_text = "\n".join(lines)
                except Exception:
                    pass
            return {
                "success": True,
                "process_id": process_id,
                "job_id": process_id,
                "stdout": log_text,
                "stderr": "",
                "running": not meta.get("stopped_at")
                and self._pid_alive(meta.get("pid")),
                "returncode": None,
                "command": meta.get("command", ""),
                "mode": meta.get("mode", "unknown"),
                "log_path": log_path,
                "persisted": True,
            }

        stdout_deque = bg.get("stdout_deque")
        stderr_deque = bg.get("stderr_deque")

        if max_lines and stdout_deque and len(stdout_deque) > max_lines:
            stdout_lines = list(stdout_deque)[-max_lines:]
            stdout_text = "\n".join(stdout_lines)
        elif stdout_deque:
            stdout_text = "\n".join(stdout_deque)
        else:
            stdout_text = ""

        if stderr_deque:
            if max_lines and len(stderr_deque) > max_lines:
                stderr_lines = list(stderr_deque)[-max_lines:]
                stderr_text = "\n".join(stderr_lines)
            else:
                stderr_text = "\n".join(stderr_deque)
        else:
            stderr_text = ""

        proc = bg["process"]
        running = proc.returncode is None

        if not running:
            self._mark_job_stopped(process_id)
            self._cleanup_process(process_id)

        return {
            "success": True,
            "process_id": process_id,
            "job_id": process_id,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "running": running,
            "returncode": proc.returncode,
            "command": bg["command"],
            "mode": bg["mode"],
            "log_path": str(bg["log_path"].relative_to(self.project_path))
            if bg.get("log_path")
            else None,
        }

    # ─── action: write ──────────────────────────────────────────

    async def _write_action(self, process_id, stdin_input):
        """向后台进程写入 stdin"""
        if not process_id:
            return {"success": False,
                    "error": "process_id is required for action=\"write\""}
        if not stdin_input:
            return {"success": False,
                    "error": "stdin_input is required for action=\"write\""}

        bg = self._background_processes.get(process_id)
        if not bg:
            return {"success": False,
                    "error": f"Process not found: {process_id}"}

        proc = bg["process"]
        if proc.returncode is not None:
            return {"success": False,
                    "error": f"Process {process_id} has already exited"}

        try:
            data = stdin_input.encode("utf-8")
            master_fd = bg.get("master_fd")
            if master_fd is not None:
                # PTY jobs read input from the master side; proc.stdin is None
                # because stdin was bound to the slave fd at spawn time.
                os.write(master_fd, data)
            else:
                proc.stdin.write(data)
                await proc.stdin.drain()
        except Exception as e:
            return {"success": False,
                    "error": f"Failed to write to process: {e}"}

        return {
            "success": True,
            "process_id": process_id,
        }

    # ─── action: kill ───────────────────────────────────────────

    async def _kill_action(self, process_id):
        """终止后台进程"""
        if not process_id:
            return {"success": False,
                    "error": "process_id is required for action=\"kill\""}

        bg = self._background_processes.get(process_id)
        if not bg:
            meta = self._read_job_meta(process_id)
            if not meta:
                return {"success": False,
                        "error": f"Process not found: {process_id}"}
            self._terminate_pid(meta.get("pid"), grouped=True)
            meta["stopped_at"] = time.time()
            self._write_job_meta(process_id, meta)
            return {
                "success": True,
                "process_id": process_id,
                "job_id": process_id,
                "returncode": None,
                "command": meta.get("command", ""),
                "persisted": True,
            }

        proc = bg["process"]
        try:
            if os.name != "nt":
                self._terminate_pid(proc.pid, grouped=True)
            else:
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
        except ProcessLookupError:
            pass

        returncode = proc.returncode
        self._mark_job_stopped(process_id)
        self._cleanup_process(process_id)

        return {
            "success": True,
            "process_id": process_id,
            "returncode": returncode,
            "command": bg["command"],
        }

    # ─── diff hook ───────────────────────────────────────────

    async def _attach_changes(self, result: Dict[str, Any]):
        """附加文件变更信息到返回结果（透明注入，最多等3秒）"""
        if not self._diff_hook:
            return
        try:
            changes = await asyncio.wait_for(
                asyncio.to_thread(self._diff_hook.post_exec),
                timeout=3.0,
            )
            if changes and changes.get("total_files", 0) > 0:
                result["_changes"] = changes
        except (asyncio.TimeoutError, Exception):
            pass

    # ─── helpers ────────────────────────────────────────────────

    async def _stream_lines(self, stream, prefix, buf, idle_timeout, process):
        """逐行读取子进程输出，实时打印 + 收集到 buf"""
        last_output = time.monotonic()
        while True:
            line = await stream.readline()
            if not line:
                break
            text = _smart_decode(line).rstrip()
            print(f"{prefix}{text}", flush=True)
            buf.append(text)
            last_output = time.monotonic()
            if idle_timeout and time.monotonic() - last_output > idle_timeout:
                if process.returncode is None:
                    process.terminate()
                break

    async def _stream_pty_reader(self, reader, buf, idle_timeout, process):
        """从 PTY reader 逐行读取"""
        last_output = time.monotonic()
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.5)
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                if idle_timeout and time.monotonic() - last_output > idle_timeout:
                    if process.returncode is None:
                        process.terminate()
                    break
                continue
            if not line:
                break
            text = _smart_decode(line).rstrip()
            if text:
                buf.append(text)
                last_output = time.monotonic()
                print(f"\u2502 {text}", flush=True)

    async def _poll_process_exit(self, proc, timeout_sec, idle_timeout,
                                  stdout_buf, stderr_buf):
        """等待进程退出，支持 idle_timeout"""
        deadline = time.monotonic() + timeout_sec
        last_output_time = time.monotonic()
        last_stdout_len = len(stdout_buf) if stdout_buf is not None else 0
        last_stderr_len = len(stderr_buf) if stderr_buf is not None else 0
        while proc.returncode is None:
            if time.monotonic() > deadline:
                raise asyncio.TimeoutError()
            if idle_timeout:
                cur_stdout_len = len(stdout_buf) if stdout_buf is not None else 0
                cur_stderr_len = len(stderr_buf) if stderr_buf is not None else 0
                if cur_stdout_len != last_stdout_len or cur_stderr_len != last_stderr_len:
                    last_output_time = time.monotonic()
                    last_stdout_len = cur_stdout_len
                    last_stderr_len = cur_stderr_len
                elif time.monotonic() - last_output_time > idle_timeout:
                    proc.terminate()
                    raise asyncio.TimeoutError(
                        f"Idle timeout ({idle_timeout}s) - no output")
            await asyncio.sleep(0.01)

    async def _reap_process(self, proc, wait_sec):
        """回收进程，先等 wait_sec 再 kill"""
        try:
            await asyncio.wait_for(proc.wait(), timeout=wait_sec)
        except (asyncio.TimeoutError, Exception):
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except Exception:
                pass

    def _apply_max_output(self, text, max_output, prefix, max_output_lines=None):
        """Apply char/line caps and archive the full output once when truncated."""
        if not text:
            return text, False

        original = text
        truncated = False

        if isinstance(max_output_lines, int) and max_output_lines > 0:
            lines = text.splitlines(keepends=True)
            if len(lines) > max_output_lines:
                text = "".join(lines[:max_output_lines])
                truncated = True

        if not _is_unlimited(max_output) and isinstance(max_output, int) and max_output > 0:
            if len(text) > max_output:
                text = text[:max_output]
                truncated = True

        if not truncated:
            return text, False

        try:
            extracts = self.project_path / ".aacode" / "extracts"
            extracts.mkdir(parents=True, exist_ok=True)
            path = extracts / f"tool_{prefix}_{uuid.uuid4().hex[:8]}.txt"
            path.write_text(original, encoding="utf-8")
            suffix = (
                f"\n\n[Output truncated; full output saved to {path}. "
                f"Use rg/sed/head/tail to inspect it, or pass full_output=true "
                f"(or a larger max_output) next time.]"
            )
            text += suffix
        except Exception:
            text += "\n\n[Output truncated; full output could not be archived.]"

        return text, True

    def _create_pty(self):
        """创建 PTY master/slave 对，失败返回 None"""
        try:
            import pty
            import tty
            master_fd, slave_fd = pty.openpty()
            try:
                tty.setraw(master_fd)
            except Exception:
                pass
            return master_fd, slave_fd
        except Exception:
            return None

    async def _create_pty_reader(self, master_fd):
        """从 PTY master fd 创建 asyncio StreamReader"""
        import fcntl
        loop = asyncio.get_running_loop()
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        reader = asyncio.StreamReader(limit=2**16)
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(
            lambda: protocol,
            os.fdopen(master_fd, 'rb', buffering=0, closefd=True),
        )
        return reader

    def _cleanup_process(self, process_id):
        """清理后台进程资源"""
        bg = self._background_processes.pop(process_id, None)
        if not bg:
            return
        for key in ("stdout_reader", "stderr_reader"):
            task = bg.get(key)
            if task and not task.done():
                task.cancel()
        handle = bg.get("log_handle")
        if handle:
            try:
                handle.close()
            except Exception:
                pass
        master_fd = bg.get("master_fd")
        if master_fd is not None:
            try:
                os.close(master_fd)
            except Exception:
                pass
