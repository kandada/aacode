# 原子工具 - 简化版
# tools/atomic_tools.py
"""
轻量级原子工具
遵循"bash是万能适配器"原则,简化实现
仅保留 run_shell，文件操作通过 shell 命令完成
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from aacode.i18n import t


class AtomicTools:
    """简化的原子工具集"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard

    async def run_shell(
        self, command: str, timeout: int = 120, stdin_input: str = None, max_output: int = None, **kwargs
    ) -> Dict[str, Any]:
        """
        执行shell命令(带安全护栏)

        Args:
            command: 要执行的shell命令
            timeout: 超时时间（秒）
            stdin_input: 传给程序的标准输入内容（可选）。程序有 input() 时使用，多行用 \\n 分隔
            max_output: 限制返回的输出最大字符数。默认None（不限制），传数字如200可限制输出

        Note: **kwargs 用于接收并忽略模型可能传入的额外参数
        """
        try:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            if timeout is None:
                if __package__ in (None, ""):
                    from config import settings
                else:
                    from ..config import settings

                timeout = settings.timeouts.shell_command

            # 安全检查
            safety_check = self.safety_guard.check_command(command)
            if not safety_check["allowed"]:
                return {
                    "error": f"Command rejected by safety guard: {safety_check['reason']}",
                    "allowed": False,
                    "command": command,
                }

            # 在项目目录下执行
            print(f"🔧 Executing command: {command}")

            # stdin 策略：有 stdin_input 时用 PIPE 喂入，否则用 DEVNULL 防阻塞
            if stdin_input:
                stdin_mode = asyncio.subprocess.PIPE
            else:
                stdin_mode = asyncio.subprocess.DEVNULL

            # 异步执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.project_path),
                stdin=stdin_mode,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            async def _stream_lines(stream, prefix, buf):
                """逐行读取子进程输出，实时打印 + 收集到 buf"""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode(errors="replace").rstrip()
                    print(f"{prefix}{text}", flush=True)
                    buf.append(text)

            def _smart_decode(data):
                import os as _os
                if _os.name != "nt":
                    return data.decode("utf-8", errors="replace")
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError:
                    return data.decode("gbk", errors="replace")

            try:
                if stdin_input:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=stdin_input.encode("utf-8")),
                        timeout=timeout,
                    )
                    stdout_text = _smart_decode(stdout)
                    stderr_text = _smart_decode(stderr)
                else:
                    stdout_buf = []
                    stderr_buf = []
                    stdout_reader = asyncio.create_task(
                        _stream_lines(process.stdout, "│ ", stdout_buf)
                    )
                    stderr_reader = asyncio.create_task(
                        _stream_lines(process.stderr, "╰ ", stderr_buf)
                    )
                    await asyncio.wait_for(process.wait(), timeout=timeout)
                    await asyncio.gather(stdout_reader, stderr_reader)
                stdout_text = "\n".join(stdout_buf)
                stderr_text = "\n".join(stderr_buf)

                # 统一返回格式：工具总是成功，返回完整的命令执行信息
                # 兼容各种"不限制"的表达：None/null/none/0/""都不限制
                stdout_truncated = False
                stderr_truncated = False
                # 处理各种表示"无限制"的值
                if max_output is None or max_output == 0 or (isinstance(max_output, str) and max_output.lower() in ('none', 'null', '')):
                    # 不截断
                    pass
                elif isinstance(max_output, int) and max_output > 0:
                    if stdout_text and len(stdout_text) > max_output:
                        stdout_text = stdout_text[:max_output]
                        stdout_truncated = True
                    if stderr_text and len(stderr_text) > max_output:
                        stderr_text = stderr_text[:max_output]
                        stderr_truncated = True

                return {
                    "success": True,  # 工具执行成功
                    "returncode": process.returncode,  # 命令退出码
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "_max_output_setting": max_output,  # 传递给后端截断逻辑
                    "command": command,
                    "working_directory": str(self.project_path),
                }
            except asyncio.TimeoutError:
                process.terminate()
                return {
                    "success": True,  # 工具执行成功
                    "error": f"Command execution timeout ({timeout}s)",
                    "timeout": True,
                    "command": command,
                    "working_directory": str(self.project_path),
                }

        except Exception as e:
            # 只有工具本身出现异常时才返回 success=False
            error_type = type(e).__name__
            error_msg = f"Tool execution exception: {error_type}: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,  # 工具执行失败
                "error": error_msg,
                "command": command,
                "working_directory": str(self.project_path),
            }