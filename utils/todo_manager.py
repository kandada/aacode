# To-Do List管理器
# utils/todo_manager.py
"""
To-Do List管理器
负责创建、更新和跟踪任务待办清单
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiofiles
import json
import re


class TodoManager:
    """To-Do List管理器"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.todo_dir = project_path / ".aacode" / "todos"
        self.todo_dir.mkdir(parents=True, exist_ok=True)
        self.current_todo_file: Optional[Path] = None
        self.todos: List[Dict] = []

    async def create_todo_list(
        self,
        task_description: str,
        project_name: Optional[str] = None,
        context_manager: Any = None,
    ) -> str:
        """
        创建待办清单

        Args:
            task_description: 任务描述
            project_name: 项目名称，如果为None则从项目路径提取
            context_manager: 上下文管理器，用于同步待办文件路径

        Returns:
            待办清单文件路径
        """
        # 生成项目名称
        if project_name is None:
            project_name = self.project_path.name
            if not project_name or project_name == ".":
                project_name = "project"

        # 清理项目名称，移除特殊字符
        clean_project_name = re.sub(r"[^\w\-_]", "_", project_name)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_project_name}_to-do-list_{timestamp}.md"
        self.current_todo_file = self.todo_dir / filename

        # 优化1：同步到上下文管理器
        if context_manager:
            context_manager.current_todo_file = self.current_todo_file

        # 优化1：简化待办清单格式，更紧凑
        todo_content = f"""# {clean_project_name} - 待办清单

**任务**: {task_description}
**创建**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 待办
- [ ] 分析需求
- [ ] 制定计划
- [ ] 执行任务

## 已完成
（暂无）

## 记录
- {datetime.now().strftime("%H:%M:%S")} 创建清单

---
*自动维护*
"""

        # 写入文件
        try:
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write(todo_content)
        except asyncio.CancelledError:
            # 异步任务被取消，静默处理
            return ""
        except Exception as e:
            print(f"⚠️  创建待办清单失败: {e}")
            return ""

        print(f"📋 创建待办清单: {self.current_todo_file.name}")

        return str(self.current_todo_file.relative_to(self.project_path))

    async def add_todo_item(
        self, item: str, priority: str = "medium", category: str = "任务"
    ) -> bool:
        """
        添加待办事项 - 优化1：增量追加，更高效

        Args:
            item: 待办事项描述
            priority: 优先级 (high/medium/low)
            category: 分类

        Returns:
            是否成功
        """
        if not self.current_todo_file or not self.current_todo_file.exists():
            print("⚠️  没有活动的待办清单文件")
            return False

        try:
            # 优化1：使用增量追加而非全文重写
            async with aiofiles.open(
                self.current_todo_file, "r", encoding="utf-8"
            ) as f:
                content = await f.read()

            # 查找待办部分
            lines = content.split("\n")
            insert_pos = -1
            for i, line in enumerate(lines):
                if line.strip() == "## 待办":
                    insert_pos = i + 1
                    break

            if insert_pos == -1:
                print("⚠️  找不到待办部分")
                return False

            # 简化格式：只保留核心信息
            priority_mark = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                priority, ""
            )
            new_item = f"- [ ] {priority_mark} **{category}**: {item}"
            lines.insert(insert_pos, new_item)

            # 写回文件
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

            # 改进：更清晰的打印信息
            # print(f"➕ {item[:50]}...")  # 旧的打印
            # 不打印，避免噪音，让调用者决定是否打印
            return True
        except Exception as e:
            print(f"⚠️  添加待办失败: {e}")
            return False

    async def mark_todo_completed(self, item_pattern: str) -> bool:
        """
        标记待办事项为完成

        Args:
            item_pattern: 待办事项匹配模式

        Returns:
            是否成功
        """
        if not self.current_todo_file:
            print("⚠️  没有活动的待办清单文件")
            return False

        # 读取现有内容
        async with aiofiles.open(self.current_todo_file, "r", encoding="utf-8") as f:
            content = await f.read()

        # 查找并更新待办事项
        lines = content.split("\n")
        updated = False

        for i, line in enumerate(lines):
            if (
                line.strip().startswith("- [ ]")
                and item_pattern.lower() in line.lower()
            ):
                # 标记为完成
                lines[i] = line.replace("- [ ]", "- [x]", 1)
                updated = True

                # 提取事项描述
                item_desc = line.replace("- [ ]", "").strip()
                item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*:\s*", "", item_desc)

                # 添加到已完成部分
                self._add_to_completed_section(lines, item_desc)

                print(f"✅ 标记完成: {item_desc[:50]}...")

        if updated:
            # 写入文件
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

        return updated

    def _add_to_completed_section(self, lines: List[str], item_desc: str):
        """添加到已完成部分"""
        # 查找已完成部分
        completed_section_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "## 已完成":
                completed_section_start = i
                break

        if completed_section_start == -1:
            return

        # 找到第一个空行或下一个标题
        insert_position = completed_section_start + 1
        for i in range(completed_section_start + 1, len(lines)):
            if lines[i].strip() == "" or lines[i].startswith("### "):
                insert_position = i
                break

        # 添加已完成事项
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_item = f"- ✅ **{timestamp}**: {item_desc}"
        lines.insert(insert_position, new_item)

    async def update_todo_item(self, old_pattern: str, new_item: str) -> bool:
        """
        更新待办事项

        Args:
            old_pattern: 原待办事项匹配模式
            new_item: 新待办事项描述

        Returns:
            是否成功
        """
        if not self.current_todo_file:
            print("⚠️  没有活动的待办清单文件")
            return False

        # 读取现有内容
        async with aiofiles.open(self.current_todo_file, "r", encoding="utf-8") as f:
            content = await f.read()

        # 查找并更新待办事项
        lines = content.split("\n")
        updated = False

        for i, line in enumerate(lines):
            if line.strip().startswith("- [ ]") and old_pattern.lower() in line.lower():
                match = re.match(
                    r"^- \[ \]\s*([🔴🟡🟢])?\s*\*\*(.*?)\*\*:\s*(.*)", line
                )
                if match:
                    priority_emoji = match.group(1) or ""
                    category = match.group(2)
                    lines[i] = f"- [ ] {priority_emoji} **{category}**: {new_item}"
                else:
                    lines[i] = f"- [ ] {new_item}"
                updated = True
                print(f"🔄 更新待办事项: {new_item[:50]}...")

        if updated:
            # 写入文件
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

        return updated

    async def add_execution_record(self, record: str) -> bool:
        """
        添加执行记录 - 优化1：简化格式，增量追加

        Args:
            record: 执行记录描述

        Returns:
            是否成功
        """
        if not self.current_todo_file or not self.current_todo_file.exists():
            return False

        try:
            # 优化1：直接追加到记录部分，不重写整个文件
            async with aiofiles.open(
                self.current_todo_file, "r", encoding="utf-8"
            ) as f:
                content = await f.read()

            lines = content.split("\n")
            record_pos = -1
            for i, line in enumerate(lines):
                if line.strip() == "## 记录":
                    record_pos = i + 1
                    break

            if record_pos == -1:
                return False

            # 简化格式：只记录时间和简短描述
            timestamp = datetime.now().strftime("%H:%M:%S")
            new_record = f"- {timestamp} {record[:80]}"
            lines.insert(record_pos, new_record)

            # 限制记录数量（最多保留最近20条）
            record_lines = [l for l in lines[record_pos:] if l.strip().startswith("-")]
            if len(record_lines) > 20:
                # 找到需要保留的行范围
                keep_count = 20
                delete_count = len(record_lines) - keep_count
                # 找到所有记录行的位置
                record_positions = [
                    j for j, l in enumerate(lines) if l.strip().startswith("-")
                ]
                # 删除最旧的记录（前面的）
                for pos in sorted(record_positions[:delete_count], reverse=True):
                    lines.pop(pos)

            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

            return True
        except Exception as e:
            print(f"⚠️  添加记录失败: {e}")
            return False

    async def get_todo_summary(self) -> Dict[str, Any]:
        """
        获取待办清单摘要

        Returns:
            摘要信息
        """
        # 如果没有活动的待办清单文件，尝试恢复最近的
        if not self.current_todo_file or not self.current_todo_file.exists():
            files = await self.list_todo_files()
            if files:
                latest_file = self.todo_dir / files[0]["filename"]
                self.current_todo_file = latest_file
            else:
                return {
                    "empty": True,
                    "message": "暂无待办清单，使用 /newtodo 创建新任务",
                }

        try:
            async with aiofiles.open(
                self.current_todo_file, "r", encoding="utf-8"
            ) as f:
                content = await f.read()

            # 统计待办事项
            total_todos = 0
            completed_todos = 0
            pending_todos = 0

            lines = content.split("\n")
            for line in lines:
                if line.strip().startswith("- [ ]"):
                    pending_todos += 1
                    total_todos += 1
                elif line.strip().startswith("- [x]"):
                    completed_todos += 1
                    total_todos += 1

            # 提取项目名称
            project_name = "未知项目"
            for line in lines:
                if line.startswith("# "):
                    project_name = line.replace("# ", "").split(" - ")[0]
                    break

            return {
                "project_name": project_name,
                "todo_file": str(self.current_todo_file.relative_to(self.project_path)),
                "total_todos": total_todos,
                "completed_todos": completed_todos,
                "pending_todos": pending_todos,
                "completion_rate": (
                    (completed_todos / total_todos * 100) if total_todos > 0 else 0
                ),
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": f"读取待办清单失败: {str(e)}"}

    async def list_todo_files(self) -> List[Dict[str, Any]]:
        """
        列出所有待办清单文件

        Returns:
            待办清单文件列表
        """
        try:
            todo_files = []
            for file_path in self.todo_dir.glob("*.md"):
                try:
                    # 读取文件头部获取基本信息
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        first_line = await f.readline()
                        second_line = await f.readline()

                        # 提取项目名称
                        project_name = "未知项目"
                        if first_line.startswith("# "):
                            project_name = first_line.replace("# ", "").split(" - ")[0]

                        # 提取创建时间
                        created_time = "未知时间"
                        if second_line.startswith("**创建时间**: "):
                            created_time = second_line.replace(
                                "**创建时间**: ", ""
                            ).strip()

                        todo_files.append(
                            {
                                "filename": file_path.name,
                                "path": str(file_path.relative_to(self.project_path)),
                                "project_name": project_name,
                                "created_time": created_time,
                                "size": file_path.stat().st_size,
                                "modified_time": datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ).isoformat(),
                            }
                        )
                except Exception:
                    continue

            # 按修改时间排序（处理None值）
            todo_files.sort(key=lambda x: float(x.get("modified_time", 0) or 0), reverse=True)
            return todo_files
        except Exception as e:
            print(f"⚠️ 列出待办清单文件失败: {e}")
            return []

    async def cleanup_old_todos(self, keep_days: int = 30) -> None:
        """
        清理旧的待办清单文件

        Args:
            keep_days: 保留天数
        """
        try:
            import time

            cutoff_time = time.time() - (keep_days * 24 * 3600)

            for todo_file in self.todo_dir.glob("*.md"):
                if todo_file.stat().st_mtime < cutoff_time:
                    try:
                        todo_file.unlink()
                        print(f"🗑️  清理旧待办清单: {todo_file.name}")
                    except Exception as e:
                        print(f"⚠️ 清理待办清单失败 {todo_file.name}: {e}")
        except Exception as e:
            print(f"⚠️ 待办清单清理失败: {e}")


# 全局待办管理器实例
_todo_managers: Dict[str, TodoManager] = {}


def get_todo_manager(project_path: Path) -> TodoManager:
    """获取项目的待办管理器"""
    project_key = str(project_path.absolute())
    if project_key not in _todo_managers:
        _todo_managers[project_key] = TodoManager(project_path)
    return _todo_managers[project_key]
