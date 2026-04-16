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
                todo_id_val = success  # add_todo_item now returns todo_id string or None
                result = {
                    "success": True,
                    "todo_id": todo_id_val,
                    "message": f"已添加待办事项 [#{todo_id_val}]: {item_desc}（完成时请用 mark_todo_completed(todo_id=\"{todo_id_val}\")）",
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
        self, item_pattern: str = None, todo_id: str = None, **kwargs
    ) -> Dict[str, Any]:
        """
        标记待办事项为完成

        Args:
            item_pattern: 待办事项匹配模式（文本）
            todo_id: 待办事项ID（如 "t1"），由 add_todo_item 返回，优先使用
            **kwargs: 兼容模型常用参数名（title/item/name/task/todo）

        Returns:
            操作结果
        """
        # 从 kwargs 提取 todo_id（兼容模型可能用的参数名）
        if not todo_id:
            todo_id = kwargs.get("todo_id") or kwargs.get("id")

        # 兼容多种参数名获取 item_pattern
        if not item_pattern:
            for key in ("title", "item", "name", "task", "todo", "description"):
                val = kwargs.get(key)
                if val:
                    item_pattern = val
                    break

        if not item_pattern and not todo_id:
            return {
                "success": False,
                "error": "缺少 todo_id 或 item_pattern 参数。建议使用 add_todo_item 返回的 todo_id。",
            }

        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            success = await todo_manager.mark_todo_completed(
                item_pattern=item_pattern or "", todo_id=todo_id
            )

            if success:
                match_info = f"[#{todo_id}]" if todo_id else item_pattern
                result = {
                    "success": True,
                    "message": f"已标记待办事项为完成: {match_info}",
                    "todo_id": todo_id,
                    "item_pattern": item_pattern,
                }
                print(f"✅ {result['message']}")
                return result
            else:
                match_info = f"[#{todo_id}]" if todo_id else item_pattern
                result = {
                    "success": False,
                    "error": f"未找到匹配的待办事项: {match_info}",
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
        添加执行记录（已废弃，过程日志由 .aacode/logs/ 承担）

        保留方法签名以向后兼容，静默返回成功。

        Returns:
            操作结果
        """
        return {
            "success": True,
            "message": "执行记录已合并到日志系统",
        }
