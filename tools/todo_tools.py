# To-Do List工具
# tools/todo_tools.py
"""
To-Do List管理工具
为Agent提供管理待办清单的能力
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio


class TodoTools:
    """To-Do List工具类"""

    def __init__(self, project_path: Path, safety_guard: Any = None):
        self.project_path = project_path
        self.safety_guard = safety_guard

    async def add_todo_item(
        self,
        description: Optional[str] = None,
        item: Optional[str] = None,
        priority: str = "medium",
        category: str = "任务",
        task_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        添加待办事项(兼容多种参数格式)

        Args:
            description: 待办事项描述(优先使用)
            item: 待办事项描述(兼容旧格式)
            title: 待办事项标题(兼容旧格式)
            priority: 优先级 (high/medium/low)
            category: 分类
            task_id: 任务ID(可选,用于关联)

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            操作结果
        """
        # 兼容多种参数格式
        title = kwargs.get("title")
        item_desc = description or item or title
        if not item_desc:
            return {
                "success": False,
                "error": "缺少待办事项描述(需要 description 或 item 参数)",
            }
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            # 如果没有活动的待办清单,尝试创建默认的
            if (
                todo_manager.current_todo_file is None
                or not todo_manager.current_todo_file.exists()
            ):
                # 尝试获取最近的待办清单文件
                files = await todo_manager.list_todo_files()
                if files:
                    # 使用最新的待办清单文件
                    latest_file = todo_manager.todo_dir / files[0]["filename"]
                    todo_manager.current_todo_file = latest_file
                else:
                    # 创建默认待办清单
                    await todo_manager.create_todo_list("默认任务", "默认项目")

            success = await todo_manager.add_todo_item(item_desc, priority, category)

            if success:
                result = {
                    "success": True,
                    "message": f"已添加待办事项: {item_desc}",
                    "item": item_desc,
                    "priority": priority,
                    "category": category,
                    "task_id": task_id,
                }
                print(f"✅ {result['message']}")
                return result
            else:
                result = {"success": False, "error": "添加待办事项失败"}
                print(f"⚠️  {result['error']}")
                return result

        except Exception as e:
            return {"success": False, "error": f"添加待办事项时出错: {str(e)}"}

    async def mark_todo_completed(
        self, item_pattern: str = None, **kwargs
    ) -> Dict[str, Any]:
        """
        标记待办事项为完成

        Args:
            item_pattern: 待办事项匹配模式
            **kwargs: 兼容模型常用参数名（title/item/name/task/todo）

        Returns:
            操作结果
        """
        # 兼容多种参数名
        if not item_pattern:
            for key in ("title", "item", "name", "task", "todo", "description"):
                val = kwargs.get(key)
                if val:
                    item_pattern = val
                    break

        if not item_pattern:
            return {
                "success": False,
                "error": "缺少待办事项匹配模式",
            }

        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            success = await todo_manager.mark_todo_completed(item_pattern)

            if success:
                result = {
                    "success": True,
                    "message": f"已标记待办事项为完成: {item_pattern}",
                    "item_pattern": item_pattern,
                }
                print(f"✅ {result['message']}")
                return result
            else:
                result = {
                    "success": False,
                    "error": f"未找到匹配的待办事项: {item_pattern}",
                }
                print(f"⚠️  {result['error']}")
                return result

        except Exception as e:
            return {"success": False, "error": f"标记待办事项完成时出错: {str(e)}"}

    async def update_todo_item(
        self, old_pattern: str, new_item: str, **kwargs
    ) -> Dict[str, Any]:
        """
        更新待办事项

        Args:
            old_pattern: 原待办事项匹配模式
            new_item: 新待办事项描述

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            操作结果
        """
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            success = await todo_manager.update_todo_item(old_pattern, new_item)

            if success:
                return {
                    "success": True,
                    "message": f"已更新待办事项: {old_pattern} -> {new_item}",
                    "old_pattern": old_pattern,
                    "new_item": new_item,
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到匹配的待办事项: {old_pattern}",
                }

        except Exception as e:
            return {"success": False, "error": f"更新待办事项时出错: {str(e)}"}

    async def get_todo_summary(self, **kwargs) -> Dict[str, Any]:
        """
        获取待办清单摘要

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            摘要信息
        """
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            summary = await todo_manager.get_todo_summary()

            return {"success": "error" not in summary, **summary}

        except Exception as e:
            return {"success": False, "error": f"获取待办清单摘要时出错: {str(e)}"}

    async def list_todo_files(self) -> Dict[str, Any]:
        """
        列出所有待办清单文件

        Returns:
            待办清单文件列表
        """
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            files = await todo_manager.list_todo_files()

            return {"success": True, "files": files, "count": len(files)}

        except Exception as e:
            return {"success": False, "error": f"列出待办清单文件时出错: {str(e)}"}

    async def add_execution_record(
        self, record: str = None, description: str = None, **kwargs
    ) -> Dict[str, Any]:
        """
        添加执行记录

        Args:
            record: 执行记录描述(优先使用)
            description: 执行记录描述(兼容旧格式)
            **kwargs: 兼容模型常用的各种参数名（task/action/result/details/content/message）

        Returns:
            操作结果
        """
        # 兼容模型传入的各种参数名，按优先级取值
        record_text = record or description
        if not record_text:
            # 尝试从 kwargs 中提取，模型可能用任意参数名
            for key in ("task", "action", "content", "message", "result", "details", "summary", "note"):
                val = kwargs.get(key)
                if val:
                    record_text = val
                    break

        if not record_text:
            # 最后兜底：把所有 kwargs 的值拼起来
            all_vals = [str(v) for v in kwargs.values() if v]
            if all_vals:
                record_text = " | ".join(all_vals)

        if not record_text:
            return {
                "success": False,
                "error": "缺少执行记录描述",
            }

        # 拼接补充信息（如果有多个字段，把其他字段也加上）
        extra_parts = []
        for key in ("result", "details", "status"):
            val = kwargs.get(key)
            if val and val != record_text:
                extra_parts.append(f"{val}")
        if extra_parts:
            record_text = f"{record_text} - {' | '.join(extra_parts)}"

        # 附加状态信息
        status = kwargs.get("status")
        if status:
            record_text = f"[{status}] {record_text}"

        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            success = await todo_manager.add_execution_record(record_text)

            if success:
                print(f"✅ 已添加执行记录: {record_text[:50]}...")
                return {
                    "success": True,
                    "message": f"已添加执行记录: {record_text[:50]}...",
                    "record": record_text,
                }
            else:
                print(f"⚠️ 添加执行记录失败")
                return {"success": False, "error": "添加执行记录失败"}

        except Exception as e:
            return {"success": False, "error": f"添加执行记录时出错: {str(e)}"}
