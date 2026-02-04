# mcp客户端
# sandbox/mcp_client.py
"""
MCP（模型上下文协议）客户端简化实现
"""
import asyncio
import json
from typing import Dict, List, Any, Optional
import aiohttp


class MCPClient:
    """MCP客户端"""

    def __init__(self,
                 server_url: str = "http://localhost:3000",
                 client_name: str = "ai_coder"):

        self.server_url = server_url.rstrip('/')
        self.client_name = client_name
        self.session_id = None
        self.tools = {}

        # HTTP会话
        self.session = None

    async def connect(self) -> bool:
        """连接到MCP服务器"""
        try:
            self.session = aiohttp.ClientSession()

            # 初始化会话
            async with self.session.post(
                    f"{self.server_url}/sessions",
                    json={"client": self.client_name}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.session_id = data.get("session_id")
                    self.tools = data.get("tools", {})

                    print(f"✅ 已连接到MCP服务器，会话ID: {self.session_id}")
                    print(f"可用工具: {list(self.tools.keys())}")

                    return True
                else:
                    print(f"❌ 连接MCP服务器失败: {response.status}")
                    return False

        except Exception as e:
            print(f"❌ 连接MCP服务器异常: {e}")
            return False

    async def disconnect(self):
        """断开连接"""
        if self.session:
            if self.session_id:
                try:
                    await self.session.delete(f"{self.server_url}/sessions/{self.session_id}")
                except:
                    pass

            await self.session.close()
            self.session = None
            self.session_id = None
            self.tools = {}

    async def list_tools(self) -> Dict[str, Any]:
        """列出可用工具"""
        if not self.session_id:
            return {"error": "未连接到MCP服务器"}

        try:
            async with self.session.get(
                    f"{self.server_url}/sessions/{self.session_id}/tools"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.tools = data.get("tools", {})
                    return {
                        "success": True,
                        "tools": self.tools,
                        "count": len(self.tools)
                    }
                else:
                    return {"error": f"获取工具列表失败: {response.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def call_tool(self,
                        tool_name: str,
                        arguments: Dict = None,
                        timeout: int = 30) -> Dict[str, Any]:
        """调用MCP工具"""
        if not self.session_id:
            return {"error": "未连接到MCP服务器"}

        if tool_name not in self.tools:
            return {"error": f"工具不存在: {tool_name}"}

        try:
            payload = {
                "tool": tool_name,
                "arguments": arguments or {}
            }

            async with self.session.post(
                    f"{self.server_url}/sessions/{self.session_id}/call",
                    json=payload,
                    timeout=timeout
            ) as response:

                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "result": data.get("result"),
                        "content": data.get("content")
                    }
                else:
                    error_text = await response.text()
                    return {
                        "error": f"工具调用失败: {response.status}",
                        "details": error_text
                    }

        except asyncio.TimeoutError:
            return {"error": f"工具调用超时 ({timeout}秒)"}
        except Exception as e:
            return {"error": str(e)}

    async def execute_cli(self,
                          command: str,
                          args: List[str] = None) -> Dict[str, Any]:
        """
        通过MCP执行CLI命令

        这是一种通用的方式：通过MCP调用系统命令
        """
        return await self.call_tool("execute_command", {
            "command": command,
            "args": args or []
        })

    async def convert_format(self,
                             input_data: Any,
                             from_format: str,
                             to_format: str) -> Dict[str, Any]:
        """格式转换工具"""
        return await self.call_tool("convert_format", {
            "input": input_data,
            "from_format": from_format,
            "to_format": to_format
        })

    async def analyze_file(self, file_path: str, analysis_type: str) -> Dict[str, Any]:
        """文件分析工具"""
        return await self.call_tool("analyze_file", {
            "file_path": file_path,
            "analysis_type": analysis_type
        })

    async def web_search(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """网络搜索工具"""
        return await self.call_tool("web_search", {
            "query": query,
            "engine": engine,
            "max_results": 5
        })


# 简化版本地MCP客户端（无需服务器）
class LocalMCPClient:
    """本地MCP客户端（用于测试或简单场景）"""

    def __init__(self):
        self.tools = {
            "execute_command": self._execute_command,
            "file_info": self._file_info,
            "text_processing": self._text_processing
        }

    async def connect(self) -> bool:
        """模拟连接"""
        print("✅ 使用本地MCP客户端")
        return True

    async def disconnect(self):
        """模拟断开"""
        pass

    async def list_tools(self) -> Dict[str, Any]:
        """列出工具"""
        return {
            "success": True,
            "tools": list(self.tools.keys()),
            "count": len(self.tools)
        }

    async def call_tool(self, tool_name: str, arguments: Dict = None) -> Dict[str, Any]:
        """调用工具"""
        if tool_name not in self.tools:
            return {"error": f"工具不存在: {tool_name}"}

        try:
            result = await self.tools[tool_name](arguments or {})
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {"error": str(e)}

    async def _execute_command(self, arguments: Dict) -> Any:
        """执行命令"""
        import subprocess

        command = arguments.get("command")
        args = arguments.get("args", [])

        if not command:
            return {"error": "未指定命令"}

        try:
            full_cmd = [command] + args
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"error": str(e)}

    async def _file_info(self, arguments: Dict) -> Any:
        """获取文件信息"""
        from pathlib import Path

        file_path = arguments.get("file_path")
        if not file_path:
            return {"error": "未指定文件路径"}

        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": "文件不存在"}

            stat = path.stat()

            return {
                "path": str(path.absolute()),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "is_file": path.is_file(),
                "is_dir": path.is_dir()
            }
        except Exception as e:
            return {"error": str(e)}

    async def _text_processing(self, arguments: Dict) -> Any:
        """文本处理"""
        text = arguments.get("text", "")
        operation = arguments.get("operation", "length")

        if operation == "length":
            return {"length": len(text)}
        elif operation == "words":
            words = text.split()
            return {"word_count": len(words)}
        elif operation == "lines":
            lines = text.split('\n')
            return {"line_count": len(lines)}
        else:
            return {"error": f"未知操作: {operation}"}





