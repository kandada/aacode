# 代码执行工具
# tools/code_tools.py
"""
代码执行和测试工具
让Agent能够编写并测试自己的代码
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import subprocess
import sys


class CodeTools:
    """代码执行和测试工具"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self.test_dir = project_path / ".aacode" / "tests"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    async def execute_python(
        self, code: str, timeout: Optional[int] = None, capture_output: bool = True, **kwargs
    ) -> Dict[str, Any]:
        """
        执行Python代码

        Args:
            code: Python代码
            timeout: 超时时间(秒),默认使用配置值
            capture_output: 是否捕获输出

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            执行结果
        """
        try:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            if timeout is None:
                from config import settings

                timeout = settings.timeouts.code_execution
            
            # 确保timeout是float类型
            timeout_float = float(timeout)

            # 安全检查
            if not self.safety_guard.is_safe_python_code(code):
                return {"error": "代码安全检查失败"}

            # 创建临时文件
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=self.test_dir,
                delete=False,
                encoding="utf-8",
            ) as f:
                # 添加必要的导入和上下文
                wrapped_code = self._wrap_code(code)
                f.write(wrapped_code)
                temp_file = Path(f.name)

            try:
                # 执行代码
                cmd = [sys.executable, str(temp_file)]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE if capture_output else None,
                    stderr=asyncio.subprocess.PIPE if capture_output else None,
                    cwd=str(self.project_path),
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=timeout_float
                    )

                    result = {
                        "success": process.returncode == 0,
                        "returncode": process.returncode,
                        "file": str(temp_file.relative_to(self.project_path)),
                    }

                    if capture_output:
                        result["stdout"] = stdout.decode("utf-8", errors="ignore")
                        result["stderr"] = stderr.decode("utf-8", errors="ignore")

                    return result

                except asyncio.TimeoutError:
                    process.terminate()
                    return {
                        "error": f"代码执行超时 ({timeout_float}秒)",
                        "file": str(temp_file.relative_to(self.project_path)),
                    }

            finally:
                # 保留文件供调试,但记录已执行
                pass

        except Exception as e:
            return {"error": str(e)}

    async def run_tests(
        self, test_path: Optional[str] = None, pattern: str = "test_*.py", **kwargs
    ) -> Dict[str, Any]:
        """
        运行测试

        Args:
            test_path: 测试文件或目录路径
            pattern: 测试文件模式

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            测试结果
        """
        try:
            if test_path:
                test_target = self.project_path / test_path
                if not test_target.exists():
                    return {"error": f"测试路径不存在: {test_path}"}
            else:
                # 运行项目中的所有测试
                test_target = self.project_path

            # 使用pytest运行测试
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(test_target),
                "-v",
                "--tb=short",  # 简短的traceback
                "-q",
            ]  # 安静模式

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path),
            )

            try:
                # 使用配置的超时时间(来自 aacode_config.yaml)
                from config import settings

                test_timeout = settings.timeouts.code_execution

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=test_timeout
                )

                output = stdout.decode("utf-8", errors="ignore")

                # 解析测试结果
                test_results = self._parse_pytest_output(output)

                return {
                    "success": process.returncode == 0,
                    "returncode": process.returncode,
                    "output": output[-2000:],  # 只返回最后部分
                    "summary": test_results,
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                }

            except asyncio.TimeoutError:
                process.terminate()
                return {"error": "测试执行超时", "success": False}

        except Exception as e:
            return {"error": str(e)}

    async def debug_code(
        self, code: str, test_inputs: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        调试代码

        Args:
            code: 要调试的代码
            test_inputs: 测试输入列表

        Returns:
            调试结果
        """
        try:
            # 创建一个调试脚本
            debug_code = f"""
import sys
import traceback

# 要调试的代码
code_to_debug = '''{code}'''

# 测试输入
test_inputs = {test_inputs or []}

def run_tests():
    results = []
    try:
        # 执行代码
        exec_globals = {{}}
        exec(code_to_debug, exec_globals)

        # 如果有测试函数,运行它
        if 'test' in exec_globals:
            for i, test_input in enumerate(test_inputs):
                try:
                    result = exec_globals['test'](*test_input)
                    results.append({{
                        'input': test_input,
                        'result': result,
                        'success': True
                    }})
                except Exception as e:
                    results.append({{
                        'input': test_input,
                        'error': str(e),
                        'success': False
                    }})
    except Exception as e:
        return {{
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }}

    return {{
        'success': True,
        'results': results
    }}

if __name__ == '__main__':
    result = run_tests()
    print(result)
"""

            # 执行调试
            return await self.execute_python(debug_code, timeout=30)

        except Exception as e:
            return {"error": str(e)}

    def _wrap_code(self, code: str) -> str:
        """包装代码,添加安全检查和上下文"""
        wrapped = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
        # 添加必要的导入
        wrapped += f"""import sys
import os
from pathlib import Path

# 设置项目路径
project_root = Path(r'{self.project_path}')
os.chdir(project_root)

"""

        # 添加要执行的代码
        wrapped += f"""
# 用户代码开始
{code}
# 用户代码结束
"""

        return wrapped

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """解析pytest输出"""
        import re

        # 匹配测试结果
        passed = len(re.findall(r"PASSED|passed", output))
        failed = len(re.findall(r"FAILED|failed", output))
        error = len(re.findall(r"ERROR|error", output))

        # 匹配总结行
        summary_match = re.search(r"(\d+) passed.*?(\d+) failed.*?(\d+) error", output)

        return {
            "passed": passed,
            "failed": failed,
            "error": error,
            "total": passed + failed + error,
        }
