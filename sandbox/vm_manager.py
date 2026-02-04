# 虚拟机管理
# sandbox/vm_manager.py
"""
虚拟机/容器管理器简化实现
用于隔离和运行潜在不安全的工具
"""
import asyncio
import tempfile
from typing import Dict, List, Any, Optional
from pathlib import Path
import shutil


class SandboxManager:
    """沙箱管理器（简化实现）"""

    def __init__(self,
                 sandbox_type: str = "local",  # local, docker, vm
                 base_dir: Optional[Path] = None):

        self.sandbox_type = sandbox_type
        self.base_dir = base_dir or Path(tempfile.gettempdir()) / "ai_coder_sandbox"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 活动沙箱
        self.active_sandboxes: Dict[str, Dict] = {}

        # 预装软件
        self.preinstalled_software = [
            "python3", "pip", "git", "curl", "wget",
            "jq",  # JSON处理器
            "ffmpeg",  # 音视频处理（可选）
            "imagemagick",  # 图像处理（可选）
            "pandoc"  # 文档转换（可选）
        ]

    async def create_sandbox(self,
                             sandbox_id: str = None,
                             software: List[str] = None) -> Dict[str, Any]:
        """
        创建沙箱环境

        Args:
            sandbox_id: 沙箱ID
            software: 需要预装的软件列表

        Returns:
            沙箱信息
        """
        sandbox_id = sandbox_id or f"sandbox_{len(self.active_sandboxes)}_{asyncio.get_event_loop().time():.0f}"

        # 创建沙箱目录
        sandbox_dir = self.base_dir / sandbox_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        # 记录沙箱信息
        sandbox_info = {
            "id": sandbox_id,
            "type": self.sandbox_type,
            "directory": str(sandbox_dir),
            "created_at": asyncio.get_event_loop().time(),
            "software": software or self.preinstalled_software,
            "status": "created"
        }

        self.active_sandboxes[sandbox_id] = sandbox_info

        print(f"🛡️  创建沙箱: {sandbox_id}")

        return {
            "success": True,
            "sandbox_id": sandbox_id,
            "directory": str(sandbox_dir),
            "software": sandbox_info["software"]
        }

    async def execute_in_sandbox(self,
                                 sandbox_id: str,
                                 command: str,
                                 timeout: int = 60) -> Dict[str, Any]:
        """
        在沙箱中执行命令

        Args:
            sandbox_id: 沙箱ID
            command: 要执行的命令
            timeout: 超时时间

        Returns:
            执行结果
        """
        if sandbox_id not in self.active_sandboxes:
            return {"error": f"沙箱不存在: {sandbox_id}"}

        sandbox_info = self.active_sandboxes[sandbox_id]
        sandbox_dir = Path(sandbox_info["directory"])

        # 根据沙箱类型执行
        if self.sandbox_type == "docker":
            return await self._execute_in_docker(sandbox_id, command, timeout)
        else:
            # 本地沙箱（简单目录隔离）
            return await self._execute_local(sandbox_dir, command, timeout)

    async def _execute_local(self, sandbox_dir: Path, command: str, timeout: int) -> Dict[str, Any]:
        """在本地目录中执行命令（简单隔离）"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(sandbox_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                return {
                    "success": process.returncode == 0,
                    "returncode": process.returncode,
                    "stdout": stdout.decode('utf-8', errors='ignore'),
                    "stderr": stderr.decode('utf-8', errors='ignore'),
                    "command": command
                }

            except asyncio.TimeoutError:
                process.terminate()
                return {
                    "error": f"命令执行超时 ({timeout}秒)",
                    "command": command
                }

        except Exception as e:
            return {"error": str(e)}

    async def _execute_in_docker(self, sandbox_id: str, command: str, timeout: int) -> Dict[str, Any]:
        """在Docker容器中执行命令"""
        try:
            import docker
            client = docker.from_env()

            # 获取或创建容器
            container_name = f"ai_coder_{sandbox_id}"

            try:
                container = client.containers.get(container_name)
            except docker.errors.NotFound:
                # 创建新容器
                container = client.containers.run(
                    "python:3.11-slim",
                    name=container_name,
                    command="sleep infinity",
                    detach=True,
                    remove=True,
                    tty=True
                )

            # 在容器中执行命令
            exec_result = container.exec_run(
                cmd=["sh", "-c", command],
                workdir="/workspace"
            )

            return {
                "success": exec_result.exit_code == 0,
                "returncode": exec_result.exit_code,
                "stdout": exec_result.output.decode('utf-8', errors='ignore'),
                "stderr": "",
                "command": command
            }

        except ImportError:
            return {"error": "docker-py未安装，无法使用Docker沙箱"}
        except Exception as e:
            return {"error": f"Docker执行失败: {str(e)}"}

    async def copy_to_sandbox(self,
                              sandbox_id: str,
                              source_path: str,
                              dest_path: str = None) -> Dict[str, Any]:
        """复制文件到沙箱"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": f"沙箱不存在: {sandbox_id}"}

        sandbox_dir = Path(self.active_sandboxes[sandbox_id]["directory"])
        source = Path(source_path)

        if not source.exists():
            return {"error": f"源文件不存在: {source_path}"}

        try:
            dest = sandbox_dir / (dest_path or source.name)

            if source.is_file():
                shutil.copy2(source, dest)
            elif source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)

            return {
                "success": True,
                "source": str(source),
                "destination": str(dest),
                "type": "file" if source.is_file() else "directory"
            }

        except Exception as e:
            return {"error": str(e)}

    async def copy_from_sandbox(self,
                                sandbox_id: str,
                                source_path: str,
                                dest_path: str) -> Dict[str, Any]:
        """从沙箱复制文件"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": f"沙箱不存在: {sandbox_id}"}

        sandbox_dir = Path(self.active_sandboxes[sandbox_id]["directory"])
        source = sandbox_dir / source_path
        dest = Path(dest_path)

        if not source.exists():
            return {"error": f"沙箱文件不存在: {source_path}"}

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)

            if source.is_file():
                shutil.copy2(source, dest)
            elif source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)

            return {
                "success": True,
                "source": str(source),
                "destination": str(dest),
                "type": "file" if source.is_file() else "directory"
            }

        except Exception as e:
            return {"error": str(e)}

    async def install_software(self,
                               sandbox_id: str,
                               software: List[str]) -> Dict[str, Any]:
        """在沙箱中安装软件"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": f"沙箱不存在: {sandbox_id}"}

        results = []

        for package in software:
            if self.sandbox_type == "docker":
                # 在Docker中安装
                result = await self.execute_in_sandbox(
                    sandbox_id,
                    f"apt-get update && apt-get install -y {package}",
                    timeout=120
                )
            else:
                # 在本地尝试安装（需要sudo权限）
                result = await self.execute_in_sandbox(
                    sandbox_id,
                    f"which {package} || echo '软件 {package} 未安装'",
                    timeout=30
                )

            results.append({
                "package": package,
                "result": result
            })

        return {
            "success": True,
            "installations": results
        }

    async def cleanup_sandbox(self, sandbox_id: str) -> Dict[str, Any]:
        """清理沙箱"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": f"沙箱不存在: {sandbox_id}"}

        try:
            sandbox_info = self.active_sandboxes.pop(sandbox_id)
            sandbox_dir = Path(sandbox_info["directory"])

            if sandbox_dir.exists():
                shutil.rmtree(sandbox_dir)

            # 如果是Docker，停止容器
            if self.sandbox_type == "docker":
                import docker
                try:
                    client = docker.from_env()
                    container_name = f"ai_coder_{sandbox_id}"
                    container = client.containers.get(container_name)
                    container.stop()
                except:
                    pass

            return {
                "success": True,
                "sandbox_id": sandbox_id,
                "message": "沙箱已清理"
            }

        except Exception as e:
            return {"error": str(e)}

    async def list_sandboxes(self) -> Dict[str, Any]:
        """列出所有沙箱"""
        return {
            "success": True,
            "sandboxes": list(self.active_sandboxes.keys()),
            "count": len(self.active_sandboxes)
        }








