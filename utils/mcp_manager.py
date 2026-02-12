# MCP工具管理器
# utils/mcp_manager.py
"""
MCP（模型上下文协议）工具管理器
支持多种MCP服务器配置和动态加载
"""

import asyncio
import json
import os
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import aiohttp
from dataclasses import dataclass, field
from sandbox.mcp_client import MCPClient, LocalMCPClient


@dataclass
class MCPServerConfig:
    """MCP服务器配置"""

    name: str
    type: str  # "sse" or "std"
    url: str = ""  # 对于SSE服务器，必须有URL
    command: str = ""  # 对于STD服务器，必须有命令
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    tools: List[str] = field(default_factory=list)
    timeout: int = 30
    retry_count: int = 3


class MCPManager:
    """MCP工具管理器"""

    def __init__(self, project_path: Path, config_file: Optional[Path] = None):
        self.project_path = project_path
        self.config_file = config_file or (project_path / "mcp_config.json")
        self.servers: Dict[str, MCPServerConfig] = {}
        self.clients: Dict[str, Union[MCPClient, LocalMCPClient]] = {}
        self.connected_servers: Dict[str, bool] = {}

        # 加载配置
        self.load_config()

    def load_config(self):
        """加载MCP配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)

                # 解析服务器配置
                for server_data in config_data.get("servers", []):
                    server_config = MCPServerConfig(**server_data)
                    self.servers[server_config.name] = server_config

            # 默认配置
            if not self.servers:
                self._load_default_config()

        except Exception as e:
            print(f"⚠️ 加载MCP配置失败: {e}")
            self._load_default_config()

    def _load_default_config(self):
        """加载默认MCP配置"""
        try:
            from config import settings

            # 从配置中加载MCP服务器
            default_servers = []

            # 添加STD服务器
            for server_data in settings.mcp.std_servers:
                command = server_data.get("command")
                if not command:
                    continue  # 跳过没有命令的STD服务器

                server_config_data = {
                    "name": server_data.get("name", "unknown"),
                    "type": "std",
                    "command": command,
                    "args": server_data.get("args", []),
                    "enabled": server_data.get("enabled", True),
                    "timeout": server_data.get("timeout", 30),
                    "retry_count": server_data.get("retry_count", 3),
                }
                default_servers.append(server_config_data)

            # 添加SSE服务器
            for server_data in settings.mcp.sse_servers:
                url = server_data.get("url")
                if not url:
                    continue  # 跳过没有URL的SSE服务器

                server_config_data = {
                    "name": server_data.get("name", "unknown"),
                    "type": "sse",
                    "url": url,
                    "enabled": server_data.get("enabled", False),
                    "timeout": server_data.get("timeout", 30),
                    "retry_count": server_data.get("retry_count", 3),
                }
                default_servers.append(server_config_data)

        except ImportError:
            # 回退到旧的默认配置
            default_servers = [
                {
                    "name": "local_tools",
                    "type": "std",
                    "command": "python",
                    "args": ["-m", "mcp.server.cli"],
                    "enabled": True,
                }
            ]

            # 只添加有环境变量的SSE服务器
            filesystem_url = os.getenv("MCP_FILESYSTEM_URL")
            if filesystem_url:
                default_servers.append(
                    {
                        "name": "filesystem",
                        "type": "sse",
                        "url": filesystem_url,
                        "enabled": True,
                    }
                )

            database_url = os.getenv("MCP_DATABASE_URL")
            if database_url:
                default_servers.append(
                    {
                        "name": "database",
                        "type": "sse",
                        "url": database_url,
                        "enabled": True,
                    }
                )

            web_search_url = os.getenv("MCP_WEB_SEARCH_URL")
            if web_search_url:
                default_servers.append(
                    {
                        "name": "web_search",
                        "type": "sse",
                        "url": web_search_url,
                        "enabled": True,
                    }
                )

        for server_data in default_servers:
            server_config = MCPServerConfig(**server_data)
            self.servers[server_config.name] = server_config

    def save_config(self):
        """保存MCP配置"""
        try:
            config_data = {
                "servers": [
                    {
                        "name": server.name,
                        "type": server.type,
                        "url": server.url,
                        "command": server.command,
                        "args": server.args,
                        "env": server.env,
                        "enabled": server.enabled,
                        "tools": server.tools,
                        "timeout": server.timeout,
                        "retry_count": server.retry_count,
                    }
                    for server in self.servers.values()
                ]
            }

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"⚠️ 保存MCP配置失败: {e}")

    async def connect_all(self) -> Dict[str, Any]:
        """连接所有启用的MCP服务器"""
        results = {}

        for server_name, server_config in self.servers.items():
            if not server_config.enabled:
                continue

            try:
                result = await self.connect_server(server_name)
                results[server_name] = result
            except Exception as e:
                results[server_name] = {"success": False, "error": str(e)}

        return results

    async def connect_server(self, server_name: str) -> Dict[str, Any]:
        """连接指定的MCP服务器"""
        if server_name not in self.servers:
            return {"success": False, "error": f"服务器配置不存在: {server_name}"}

        server_config = self.servers[server_name]

        # 如果已经连接，先断开
        if server_name in self.clients:
            await self.disconnect_server(server_name)

        try:
            # 创建客户端
            if server_config.type == "sse":
                # 检查URL是否有效
                if not server_config.url:
                    return {
                        "success": False,
                        "error": f"SSE服务器 '{server_name}' 缺少URL配置",
                    }
                client = MCPClient(
                    server_url=server_config.url, client_name=f"ai_coder_{server_name}"
                )
            elif server_config.type == "std":
                client = LocalMCPClient()
            else:
                return {
                    "success": False,
                    "error": f"不支持的MCP服务器类型: {server_config.type}",
                }

            # 连接服务器
            if server_config.type == "std":
                # 对于STD类型，可能需要启动子进程
                if server_config.command:
                    # 这里可以扩展为启动子进程
                    pass

                connected = await client.connect()
            else:
                connected = await client.connect()

            if connected:
                self.clients[server_name] = client
                self.connected_servers[server_name] = True

                # 获取工具列表
                tools_result = await client.list_tools()

                return {
                    "success": True,
                    "server_name": server_name,
                    "server_type": server_config.type,
                    "tools": tools_result.get("tools", {}),
                    "tools_count": tools_result.get("count", 0),
                }
            else:
                return {"success": False, "error": f"连接MCP服务器失败: {server_name}"}

        except Exception as e:
            return {"success": False, "error": f"连接MCP服务器异常: {str(e)}"}

    async def disconnect_server(self, server_name: str):
        """断开MCP服务器连接"""
        if server_name in self.clients:
            try:
                await self.clients[server_name].disconnect()
                del self.clients[server_name]
                self.connected_servers[server_name] = False
            except Exception as e:
                print(f"⚠️ 断开MCP服务器失败: {e}")

    async def disconnect_all(self):
        """断开所有MCP服务器连接"""
        for server_name in list(self.clients.keys()):
            await self.disconnect_server(server_name)

    async def list_available_tools(self) -> Dict[str, Any]:
        """列出所有可用的MCP工具"""
        all_tools = {}

        for server_name, client in self.clients.items():
            try:
                tools_result = await client.list_tools()
                if tools_result.get("success"):
                    server_tools = tools_result.get("tools", {})
                    for tool_name, tool_info in server_tools.items():
                        # 添加服务器前缀避免冲突
                        full_tool_name = f"{server_name}.{tool_name}"
                        all_tools[full_tool_name] = {
                            "server": server_name,
                            "tool": tool_name,
                            "info": tool_info,
                        }
            except Exception as e:
                print(f"⚠️ 获取 {server_name} 工具列表失败: {e}")

        return {
            "success": True,
            "tools": all_tools,
            "count": len(all_tools),
            "connected_servers": list(self.clients.keys()),
        }

    async def call_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """调用MCP工具"""
        try:
            # 解析工具名称
            if "." in tool_name:
                server_name, actual_tool_name = tool_name.split(".", 1)
            else:
                # 如果没有服务器前缀，在所有服务器中查找
                for server_name, client in self.clients.items():
                    tools_result = await client.list_tools()
                    if tool_name in tools_result.get("tools", {}):
                        actual_tool_name = tool_name
                        break
                else:
                    return {"success": False, "error": f"工具不存在: {tool_name}"}

            if server_name not in self.clients:
                return {"success": False, "error": f"MCP服务器未连接: {server_name}"}

            client = self.clients[server_name]
            result = await client.call_tool(actual_tool_name, arguments or {})

            # 添加服务器信息
            result["server_name"] = server_name
            result["tool_name"] = actual_tool_name

            return result

        except Exception as e:
            return {"success": False, "error": f"调用MCP工具失败: {str(e)}"}

    async def get_server_status(self) -> Dict[str, Any]:
        """获取所有服务器状态"""
        status = {}

        for server_name, server_config in self.servers.items():
            status[server_name] = {
                "name": server_name,
                "type": server_config.type,
                "enabled": server_config.enabled,
                "connected": self.connected_servers.get(server_name, False),
                "url": server_config.url,
                "command": server_config.command,
            }

            if server_name in self.clients:
                try:
                    tools_result = await self.clients[server_name].list_tools()
                    status[server_name]["tools_count"] = tools_result.get("count", 0)
                    status[server_name]["last_check"] = asyncio.get_event_loop().time()
                except Exception as e:
                    status[server_name]["error"] = str(e)

        return {
            "success": True,
            "servers": status,
            "total_servers": len(self.servers),
            "connected_servers": len(self.clients),
        }

    async def add_server(self, server_config: MCPServerConfig) -> Dict[str, Any]:
        """添加新的MCP服务器"""
        try:
            self.servers[server_config.name] = server_config
            self.save_config()

            # 如果启用，立即连接
            if server_config.enabled:
                return await self.connect_server(server_config.name)
            else:
                return {
                    "success": True,
                    "message": f"MCP服务器已添加但未启用: {server_config.name}",
                }

        except Exception as e:
            return {"success": False, "error": f"添加MCP服务器失败: {str(e)}"}

    async def remove_server(self, server_name: str) -> Dict[str, Any]:
        """移除MCP服务器"""
        try:
            # 先断开连接
            if server_name in self.clients:
                await self.disconnect_server(server_name)

            # 移除配置
            if server_name in self.servers:
                del self.servers[server_name]
                self.save_config()

            return {"success": True, "message": f"MCP服务器已移除: {server_name}"}

        except Exception as e:
            return {"success": False, "error": f"移除MCP服务器失败: {str(e)}"}

    async def enable_server(self, server_name: str) -> Dict[str, Any]:
        """启用MCP服务器"""
        if server_name not in self.servers:
            return {"success": False, "error": f"服务器不存在: {server_name}"}

        self.servers[server_name].enabled = True
        self.save_config()

        return await self.connect_server(server_name)

    async def disable_server(self, server_name: str) -> Dict[str, Any]:
        """禁用MCP服务器"""
        if server_name not in self.servers:
            return {"success": False, "error": f"服务器不存在: {server_name}"}

        # 断开连接
        if server_name in self.clients:
            await self.disconnect_server(server_name)

        # 更新配置
        self.servers[server_name].enabled = False
        self.save_config()

        return {"success": True, "message": f"MCP服务器已禁用: {server_name}"}

    async def auto_discover_servers(self) -> Dict[str, Any]:
        """自动发现本地MCP服务器"""
        discovered = []

        # 检查常见的本地端口
        common_ports = [3000, 3001, 3002, 3003, 8080, 8081, 8082]

        for port in common_ports:
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as session:
                    async with session.get(
                        f"http://localhost:{port}/health"
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            server_name = data.get("name", f"localhost_{port}")

                            if server_name not in self.servers:
                                server_config = MCPServerConfig(
                                    name=server_name,
                                    type="sse",
                                    url=f"http://localhost:{port}",
                                    enabled=False,
                                )
                                discovered.append(server_config)

            except Exception:
                continue

        # 添加发现的配置
        for server_config in discovered:
            self.servers[server_config.name] = server_config

        if discovered:
            self.save_config()

        return {"success": True, "discovered": discovered, "count": len(discovered)}

    async def cleanup(self):
        """清理资源"""
        await self.disconnect_all()
