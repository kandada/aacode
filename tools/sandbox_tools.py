# 沙箱执行工具
# tools/sandbox_tools.py
"""
沙箱工具集
用于在隔离环境中运行工具
"""

import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path

from sandbox.vm_manager import SandboxManager
from sandbox.mcp_client import MCPClient, LocalMCPClient


class SandboxTools:
    """沙箱工具集"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard

        # 沙箱管理器
        import os

        sandbox_type = os.getenv("SANDBOX_TYPE", "docker")  # 默认使用Docker沙箱
        self.sandbox_manager = SandboxManager(
            sandbox_type=sandbox_type, base_dir=project_path / ".aacode" / "sandboxes"
        )

        # MCP客户端
        self.mcp_client: MCPClient | LocalMCPClient = LocalMCPClient()  # 默认使用本地客户端

        # 默认沙箱
        self.default_sandbox_id = None

    async def run_in_sandbox(
        self, command: str, sandbox_id: str | None = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """
        在沙箱中运行命令

        Args:
            command: 要执行的命令
            sandbox_id: 沙箱ID(为空则使用默认沙箱)
            timeout: 超时时间

        Returns:
            执行结果
        """
        # 安全检查
        safety_check = self.safety_guard.check_command(command)
        if not safety_check["allowed"] and self.sandbox_manager.sandbox_type == "local":
            return {
                "error": f"命令被安全护栏拒绝: {safety_check['reason']}",
                "suggestion": "请使用Docker沙箱运行潜在危险命令",
            }

        # 获取或创建沙箱
        if not sandbox_id:
            if not self.default_sandbox_id:
                result = await self.sandbox_manager.create_sandbox(
                    sandbox_id="default_sandbox"
                )
                if result["success"]:
                    self.default_sandbox_id = result["sandbox_id"]
                else:
                    return result

            sandbox_id = self.default_sandbox_id or "default_sandbox"

        print(f"🛡️  在沙箱 {sandbox_id} 中执行: {command[:50]}...")

        # 在沙箱中执行命令
        return await self.sandbox_manager.execute_in_sandbox(
            sandbox_id or "default_sandbox", command, timeout
        )

    async def install_package(
        self, package: str, package_manager: str = "pip", sandbox_id: str | None = None
    ) -> Dict[str, Any]:
        """
        在沙箱中安装软件包

        Args:
            package: 包名
            package_manager: 包管理器 (pip, apt, npm, etc.)
            sandbox_id: 沙箱ID

        Returns:
            安装结果
        """
        # 构建安装命令
        if package_manager == "pip":
            command = f"pip install {package}"
        elif package_manager == "apt":
            command = f"apt-get update && apt-get install -y {package}"
        elif package_manager == "npm":
            command = f"npm install -g {package}"
        elif package_manager == "yarn":
            command = f"yarn global add {package}"
        else:
            return {"error": f"不支持的包管理器: {package_manager}"}

        return await self.run_in_sandbox(command, sandbox_id, timeout=120)

    async def call_mcp(
        self, tool_name: str, arguments: Dict[Any, Any] | None = None, mcp_server: str | None = None
    ) -> Dict[str, Any]:
        """
        调用MCP工具

        Args:
            tool_name: MCP工具名
            arguments: 工具参数
            mcp_server: MCP服务器地址

        Returns:
            调用结果
        """
        print(f"🔌 调用MCP工具: {tool_name}")

        # 连接到MCP服务器(如果需要)
        if mcp_server and isinstance(self.mcp_client, LocalMCPClient):
            # 切换到远程MCP客户端
            self.mcp_client = MCPClient(server_url=mcp_server)

        # 确保已连接
        if isinstance(self.mcp_client, MCPClient):
            if not self.mcp_client.session_id:
                connected = await self.mcp_client.connect()
                if not connected:
                    return {"error": "无法连接到MCP服务器"}
        else:
            # LocalMCPClient always connects successfully
            await self.mcp_client.connect()

        # 调用工具
        return await self.mcp_client.call_tool(tool_name, arguments or {})

    async def run_unsafe_script(
        self, script: str, language: str = "python", sandbox_id: str | None = None
    ) -> Dict[str, Any]:
        """
        运行潜在不安全的脚本

        Args:
            script: 脚本代码
            language: 脚本语言
            sandbox_id: 沙箱ID

        Returns:
            执行结果
        """
        # 根据语言创建临时脚本文件
        extension_map = {
            "python": ".py",
            "bash": ".sh",
            "javascript": ".js",
            "node": ".js",
        }

        extension = extension_map.get(language, ".txt")

        # 创建临时文件
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=extension,
            dir=self.project_path / ".aacode" / "temp",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            # 构建执行命令
            if language == "python":
                command = f"python {script_path}"
            elif language == "bash":
                command = f"bash {script_path}"
            elif language == "javascript" or language == "node":
                command = f"node {script_path}"
            else:
                return {"error": f"不支持的语言: {language}"}

            # 在沙箱中执行
            result = await self.run_in_sandbox(command, sandbox_id)

            # 添加脚本信息
            result["script_path"] = script_path
            result["language"] = language

            return result

        finally:
            # 不删除文件,供调试使用
            pass

    async def create_isolated_environment(
        self, sandbox_id: str | None = None, packages: List[str] | None = None
    ) -> Dict[str, Any]:
        """
        创建隔离的Python环境

        Args:
            sandbox_id: 沙箱ID
            packages: 要安装的Python包列表

        Returns:
            环境信息
        """
        sandbox_id = sandbox_id or f"venv_{asyncio.get_event_loop().time():.0f}"

        # 创建沙箱
        result = await self.sandbox_manager.create_sandbox(sandbox_id=sandbox_id)

        if not result["success"]:
            return result

        # 创建虚拟环境
        commands = ["python -m venv venv", "source venv/bin/activate"]

        # 安装包
        if packages:
            for package in packages:
                commands.append(f"pip install {package}")

        # 执行命令
        for cmd in commands:
            cmd_result = await self.sandbox_manager.execute_in_sandbox(
                sandbox_id, cmd, timeout=120
            )
            if not cmd_result.get("success"):
                return {
                    "error": f"创建环境失败: {cmd_result.get('error', '未知错误')}",
                    "command": cmd,
                    "sandbox_id": sandbox_id,
                }

        return {
            "success": True,
            "sandbox_id": sandbox_id,
            "environment": "venv",
            "packages": packages or [],
            "message": f"隔离环境创建成功,ID: {sandbox_id}",
        }

    async def cleanup_all_sandboxes(self) -> Dict[str, Any]:
        """清理所有沙箱"""
        sandboxes = await self.sandbox_manager.list_sandboxes()

        results = []
        for sandbox_id in sandboxes.get("sandboxes", []):
            result = await self.sandbox_manager.cleanup_sandbox(sandbox_id)
            results.append({"sandbox_id": sandbox_id, "result": result})

        # 重置默认沙箱
        self.default_sandbox_id = None

        return {"success": True, "cleaned_sandboxes": results, "count": len(results)}
