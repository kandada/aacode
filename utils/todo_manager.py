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
        self.todo_counter: int = 0  # 自增ID计数器

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

        # 重置ID计数器
        self.todo_counter = 0

        # 简化待办清单格式：只保留待办和已完成，去掉记录section
        todo_content = f"""# {clean_project_name} - 待办清单

**任务**: {task_description}
**创建**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 待办

## 已完成
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
    ) -> Optional[str]:
        """
        添加待办事项

        Args:
            item: 待办事项描述
            priority: 优先级 (high/medium/low)
            category: 分类

        Returns:
            成功返回 todo_id（如 "t1"），失败返回 None
        """
        if not self.current_todo_file or not self.current_todo_file.exists():
            print("⚠️  没有活动的待办清单文件")
            return None

        try:
            async with aiofiles.open(
                self.current_todo_file, "r", encoding="utf-8"
            ) as f:
                content = await f.read()

            # 首次添加时从文件恢复计数器
            if self.todo_counter == 0:
                self._load_counter(content)

            # 查找待办部分
            lines = content.split("\n")
            insert_pos = -1
            for i, line in enumerate(lines):
                if line.strip() == "## 待办":
                    insert_pos = i + 1
                    break

            if insert_pos == -1:
                print("⚠️  找不到待办部分")
                return None

            # 生成 todo_id
            self.todo_counter += 1
            todo_id = f"t{self.todo_counter}"

            # 格式：带 [#tN] 标记
            priority_mark = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                priority, ""
            )
            new_item = f"- [ ] {priority_mark} **{category}** [#{todo_id}]: {item}"
            lines.insert(insert_pos, new_item)

            # 写回文件
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

            return todo_id
        except Exception as e:
            print(f"⚠️  添加待办失败: {e}")
            return None

    def _load_counter(self, content: str) -> None:
        """从文件内容中恢复 todo_counter（取最大的 tN 编号）"""
        matches = re.findall(r'\[#t(\d+)\]', content)
        if matches:
            self.todo_counter = max(int(n) for n in matches)

    async def mark_todo_completed(self, item_pattern: str = "", todo_id: Optional[str] = None) -> bool:
        """
        标记待办事项为完成

        匹配策略（按优先级）：
        1. 如果传了 todo_id，精确查找 [#tN] 标记
        2. 完整 pattern 文本包含匹配
        3. 关键词模糊匹配（fallback）

        Args:
            item_pattern: 待办事项匹配模式（文本）
            todo_id: 待办事项ID（如 "t1"），由 add_todo_item 返回，优先使用

        Returns:
            是否成功
        """
        if not self.current_todo_file:
            print("⚠️  没有活动的待办清单文件")
            return False

        # 读取现有内容
        async with aiofiles.open(self.current_todo_file, "r", encoding="utf-8") as f:
            content = await f.read()

        lines = content.split("\n")
        updated = False

        # 策略1：todo_id 精确匹配
        if todo_id:
            tag = f"[#{todo_id}]"
            for i, line in enumerate(lines):
                if line.strip().startswith("- [ ]") and tag in line:
                    lines[i] = line.replace("- [ ]", "- [x]", 1)
                    updated = True
                    item_desc = line.replace("- [ ]", "").strip()
                    item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*\[#\w+\]:\s*", "", item_desc)
                    self._add_to_completed_section(lines, item_desc, todo_id)
                    print(f"✅ 标记完成 [#{todo_id}]: {item_desc[:50]}...")
                    break

        # 策略2：完整 pattern 文本包含匹配
        if not updated and item_pattern:
            pattern_lower = item_pattern.lower()
            for i, line in enumerate(lines):
                if (
                    line.strip().startswith("- [ ]")
                    and pattern_lower in line.lower()
                ):
                    lines[i] = line.replace("- [ ]", "- [x]", 1)
                    updated = True
                    # 提取 todo_id（如果有）
                    id_match = re.search(r'\[#(t\d+)\]', line)
                    matched_id = id_match.group(1) if id_match else None
                    item_desc = line.replace("- [ ]", "").strip()
                    item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*(\[#\w+\]:\s*)?", "", item_desc)
                    self._add_to_completed_section(lines, item_desc, matched_id)
                    print(f"✅ 标记完成: {item_desc[:50]}...")

        # 策略3：关键词模糊匹配（只标记第一个命中的）
        if not updated and item_pattern:
            pattern_lower = item_pattern.lower()
            # 提取关键词（停用词用子串匹配，解决中文分词粗糙的问题）
            stop_words = {"的", "了", "一个", "简单", "请", "写", "创建", "程序", "文件", "python", "py"}
            raw_words = [w for w in re.split(r'[\s,，。、]+', pattern_lower) if w and len(w) > 1]
            # 对每个词，过滤掉包含停用词的部分
            keywords = []
            for w in raw_words:
                # 如果整个词就是停用词，跳过
                if w in stop_words:
                    continue
                # 去掉词中包含的停用词子串
                cleaned = w
                for sw in stop_words:
                    cleaned = cleaned.replace(sw, "")
                if cleaned and len(cleaned) > 1:
                    keywords.append(cleaned)

            if keywords:
                for i, line in enumerate(lines):
                    if line.strip().startswith("- [ ]"):
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in keywords):
                            lines[i] = line.replace("- [ ]", "- [x]", 1)
                            updated = True
                            id_match = re.search(r'\[#(t\d+)\]', line)
                            matched_id = id_match.group(1) if id_match else None
                            item_desc = line.replace("- [ ]", "").strip()
                            item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*(\[#\w+\]:\s*)?", "", item_desc)
                            self._add_to_completed_section(lines, item_desc, matched_id)
                            print(f"✅ 模糊匹配标记完成: {item_desc[:50]}...")
                            break

        if updated:
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write("\n".join(lines))

        return updated

    def _add_to_completed_section(self, lines: List[str], item_desc: str, todo_id: Optional[str] = None):
        """添加到已完成部分"""
        # 查找已完成部分
        completed_section_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "## 已完成":
                completed_section_start = i
                break

        if completed_section_start == -1:
            return

        # 找到插入位置（已完成标题的下一行）
        insert_position = completed_section_start + 1

        # 添加已完成事项（带 todo_id 标记）
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        id_tag = f" [#{todo_id}]" if todo_id else ""
        new_item = f"- ✅ **{timestamp}**{id_tag}: {item_desc}"
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
        添加执行记录（已废弃）

        记录section已移除，过程日志由 .aacode/logs/ 承担。
        保留方法签名以向后兼容，静默返回成功。

        Args:
            record: 执行记录描述（不再写入）

        Returns:
            始终返回 True
        """
        return True

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
                        if second_line.startswith("**创建**: "):
                            created_time = second_line.replace("**创建**: ", "").strip()

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
            todo_files.sort(
                key=lambda x: x.get("modified_time", "") or "", reverse=True
            )
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
