# 文件操作
# utils/file_ops.py
"""
文件操作辅助工具
"""

import asyncio
import aiofiles
import aiofiles.os
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable, Coroutine
import shutil
import json
import hashlib


class FileOps:
    """异步文件操作工具类"""

    @staticmethod
    async def read_file(file_path: Union[str, Path], encoding: str = "utf-8") -> str:
        """
        异步读取文件

        Args:
            file_path: 文件路径
            encoding: 编码格式

        Returns:
            文件内容
        """
        try:
            async with aiofiles.open(file_path, "r", encoding=encoding) as f:
                return await f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"文件不存在: {file_path}")
        except Exception as e:
            raise Exception(f"读取文件失败: {str(e)}")

    @staticmethod
    async def write_file(
        file_path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        append: bool = False,
    ) -> bool:
        """
        异步写入文件

        Args:
            file_path: 文件路径
            content: 内容
            encoding: 编码格式
            append: 是否追加模式

        Returns:
            是否成功
        """
        try:
            mode = "a" if append else "w"
            async with aiofiles.open(file_path, mode, encoding=encoding) as f:
                await f.write(content)
            return True
        except Exception as e:
            raise Exception(f"写入文件失败: {str(e)}")

    @staticmethod
    async def list_files(
        directory: Union[str, Path], pattern: str = "*", recursive: bool = False
    ) -> List[str]:
        """
        列出文件

        Args:
            directory: 目录路径
            pattern: 文件匹配模式
            recursive: 是否递归查找

        Returns:
            文件路径列表
        """
        try:
            dir_path = Path(directory)

            if not recursive:
                # 非递归查找
                if pattern == "*":
                    items = [p for p in dir_path.iterdir() if p.is_file()]
                else:
                    items = list(dir_path.glob(pattern))
            else:
                # 递归查找
                items = list(dir_path.rglob(pattern))

            return [str(p.relative_to(dir_path)) for p in items if p.is_file()]
        except Exception as e:
            raise Exception(f"列出文件失败: {str(e)}")

    @staticmethod
    async def file_exists(file_path: Union[str, Path]) -> bool:
        """检查文件是否存在"""
        return await aiofiles.os.path.exists(file_path)

    @staticmethod
    async def is_file(file_path: Union[str, Path]) -> bool:
        """检查是否是文件"""
        try:
            return await aiofiles.os.path.isfile(file_path)
        except:
            return False

    @staticmethod
    async def is_dir(directory: Union[str, Path]) -> bool:
        """检查是否是目录"""
        try:
            return await aiofiles.os.path.isdir(directory)
        except:
            return False

    @staticmethod
    async def get_file_size(file_path: Union[str, Path]) -> int:
        """获取文件大小"""
        try:
            stat = await aiofiles.os.stat(file_path)
            return stat.st_size
        except:
            return 0

    @staticmethod
    async def get_file_hash(file_path: Union[str, Path], algorithm: str = "md5") -> str:
        """计算文件哈希值"""
        try:
            hash_func = hashlib.new(algorithm)

            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(8192):
                    hash_func.update(chunk)

            return hash_func.hexdigest()
        except Exception as e:
            raise Exception(f"计算文件哈希失败: {str(e)}")

    @staticmethod
    async def create_dir(directory: Union[str, Path], parents: bool = True) -> bool:
        """创建目录"""
        try:
            dir_path = Path(directory)
            await aiofiles.os.makedirs(dir_path, exist_ok=True, mode=0o755)
            return True
        except Exception as e:
            raise Exception(f"创建目录失败: {str(e)}")

    @staticmethod
    async def copy_file(
        source: Union[str, Path], destination: Union[str, Path], overwrite: bool = True
    ) -> bool:
        """复制文件"""
        try:
            src = Path(source)
            dst = Path(destination)

            if not await FileOps.file_exists(src):
                raise FileNotFoundError(f"源文件不存在: {src}")

            if await FileOps.file_exists(dst) and not overwrite:
                raise FileExistsError(f"目标文件已存在: {dst}")

            # 确保目标目录存在
            await FileOps.create_dir(dst.parent)

            # 复制文件
            async with aiofiles.open(src, "rb") as f_src:
                content = await f_src.read()
                async with aiofiles.open(dst, "wb") as f_dst:
                    await f_dst.write(content)

            return True
        except Exception as e:
            raise Exception(f"复制文件失败: {str(e)}")

    @staticmethod
    async def move_file(
        source: Union[str, Path], destination: Union[str, Path], overwrite: bool = True
    ) -> bool:
        """移动文件"""
        try:
            src = Path(source)
            dst = Path(destination)

            if not await FileOps.file_exists(src):
                raise FileNotFoundError(f"源文件不存在: {src}")

            if await FileOps.file_exists(dst) and not overwrite:
                raise FileExistsError(f"目标文件已存在: {dst}")

            # 确保目标目录存在
            await FileOps.create_dir(dst.parent)

            # 移动文件
            shutil.move(str(src), str(dst))

            return True
        except Exception as e:
            raise Exception(f"移动文件失败: {str(e)}")

    @staticmethod
    async def delete_file(file_path: Union[str, Path]) -> bool:
        """删除文件"""
        try:
            path = Path(file_path)

            if await FileOps.file_exists(path):
                await aiofiles.os.remove(path)

            return True
        except Exception as e:
            raise Exception(f"删除文件失败: {str(e)}")

    @staticmethod
    async def delete_dir(directory: Union[str, Path], recursive: bool = False) -> bool:
        """删除目录"""
        try:
            dir_path = Path(directory)

            if not await FileOps.is_dir(dir_path):
                return True  # 目录不存在，视为成功

            if recursive:
                # 递归删除
                shutil.rmtree(dir_path)
            else:
                # 只删除空目录
                await aiofiles.os.rmdir(dir_path)

            return True
        except Exception as e:
            raise Exception(f"删除目录失败: {str(e)}")

    @staticmethod
    async def search_in_file(
        file_path: Union[str, Path], pattern: str, case_sensitive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        在文件中搜索文本

        Args:
            file_path: 文件路径
            pattern: 搜索模式（正则表达式）
            case_sensitive: 是否区分大小写

        Returns:
            匹配结果列表
        """
        import re

        try:
            content = await FileOps.read_file(file_path)

            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            matches = []
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                for match in regex.finditer(line):
                    matches.append(
                        {
                            "line": i,
                            "column": match.start() + 1,
                            "match": match.group(),
                            "context": line[
                                max(0, match.start() - 20) : match.end() + 20
                            ],
                        }
                    )

            return matches
        except Exception as e:
            raise Exception(f"文件搜索失败: {str(e)}")

    @staticmethod
    async def read_json(file_path: Union[str, Path]) -> Any:
        """读取JSON文件"""
        try:
            content = await FileOps.read_file(file_path)
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析失败: {str(e)}")
        except Exception as e:
            raise Exception(f"读取JSON文件失败: {str(e)}")

    @staticmethod
    async def write_json(
        file_path: Union[str, Path],
        data: Any,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> bool:
        """写入JSON文件"""
        try:
            content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
            return await FileOps.write_file(file_path, content)
        except Exception as e:
            raise Exception(f"写入JSON文件失败: {str(e)}")

    @staticmethod
    async def backup_file(
        file_path: Union[str, Path],
        backup_dir: Optional[Union[str, Path]] = None,
        suffix: str = ".bak",
    ) -> str:
        """
        备份文件

        Args:
            file_path: 文件路径
            backup_dir: 备份目录（为空则在原目录）
            suffix: 备份文件后缀

        Returns:
            备份文件路径
        """
        try:
            src = Path(file_path)

            if not await FileOps.file_exists(src):
                raise FileNotFoundError(f"文件不存在: {src}")

            # 确定备份路径
            if backup_dir:
                backup_path = Path(backup_dir) / (src.name + suffix)
                await FileOps.create_dir(backup_dir)
            else:
                backup_path = src.with_suffix(src.suffix + suffix)

            # 复制文件
            await FileOps.copy_file(src, backup_path)

            return str(backup_path)
        except Exception as e:
            raise Exception(f"备份文件失败: {str(e)}")

    @staticmethod
    async def watch_file(
        file_path: Union[str, Path],
        callback: Callable[[str], Coroutine],
        check_interval: float = 1.0,
    ):
        """
        监视文件变化

        Args:
            file_path: 文件路径
            callback: 变化回调函数
            check_interval: 检查间隔（秒）
        """
        last_mtime = 0
        last_hash = ""

        while True:
            try:
                if await FileOps.file_exists(file_path):
                    # 获取修改时间和哈希
                    stat = await aiofiles.os.stat(file_path)
                    current_mtime = stat.st_mtime

                    if current_mtime > last_mtime:
                        # 文件可能已修改，检查哈希
                        current_hash = await FileOps.get_file_hash(file_path)

                        if current_hash != last_hash:
                            # 文件内容确实变化了
                            content = await FileOps.read_file(file_path)
                            await callback(content)

                            last_hash = current_hash

                        last_mtime = current_mtime

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"文件监视错误: {e}")
                await asyncio.sleep(check_interval)


# 方便的函数别名
read_file = FileOps.read_file
write_file = FileOps.write_file
list_files = FileOps.list_files
file_exists = FileOps.file_exists
is_file = FileOps.is_file
is_dir = FileOps.is_dir
get_file_size = FileOps.get_file_size
get_file_hash = FileOps.get_file_hash
create_dir = FileOps.create_dir
copy_file = FileOps.copy_file
move_file = FileOps.move_file
delete_file = FileOps.delete_file
delete_dir = FileOps.delete_dir
search_in_file = FileOps.search_in_file
read_json = FileOps.read_json
write_json = FileOps.write_json
backup_file = FileOps.backup_file
watch_file = FileOps.watch_file
