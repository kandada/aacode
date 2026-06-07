# To-Do List工具
# tools/todo_tools.py
"""
To-Do List管理工具
为Agent提供管理待办清单的能力
支持按 session_id 隔离多个会话
"""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import asyncio


class TodoTools:
    """To-Do List工具类"""

    def __init__(self, project_path: Path, safety_guard: Any = None,
                 get_session_id: Optional[Callable[[], Optional[str]]] = None):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self._get_session_id = get_session_id

    def _session_id(self) -> Optional[str]:
        if self._get_session_id:
            try:
                return self._get_session_id()
            except Exception:
                pass
        return None

    async def add_todo_item(
        self,
        description: Optional[str] = None,
        item: Optional[str] = None,
        priority: str = "medium",
        category: str = "Task",
        task_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        title = kwargs.get("title")
        item_desc = description or item or title
        if not item_desc:
            return {
                "success": False,
                "error": "Missing todo item description (need description or item param)",
            }
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)
            session_id = self._session_id()

            if session_id:
                todo_file = todo_manager._resolve_todo_file(session_id)
            else:
                todo_file = todo_manager.current_todo_file

            if todo_file is None or not todo_file.exists():
                files = await todo_manager.list_todo_files()
                if files:
                    latest_file = todo_manager.todo_dir / files[0]["filename"]
                    todo_manager.current_todo_file = latest_file
                else:
                    await todo_manager.create_todo_list("Default Task", "Default Project",
                                                        session_id=session_id)

            success = await todo_manager.add_todo_item(item_desc, priority, category,
                                                       session_id=session_id)

            if success:
                todo_id_val = success
                result = {
                    "success": True,
                    "todo_id": todo_id_val,
                    "message": f"Added todo item [#{todo_id_val}]: {item_desc} (use mark_todo_completed(todo_id=\"{todo_id_val}\") when done)",
                    "item": item_desc,
                    "priority": priority,
                    "category": category,
                    "task_id": task_id,
                }
                print(f"✅ {result['message']}")
                return result
            else:
                result = {"success": False, "error": "Add todo item failed"}
                print(f"⚠️  {result['error']}")
                return result

        except Exception as e:
            return {"success": False, "error": f"Error adding todo item: {str(e)}"}

    async def mark_todo_completed(
        self, item_pattern: str = None, todo_id: str = None, **kwargs
    ) -> Dict[str, Any]:
        if not todo_id:
            todo_id = kwargs.get("todo_id") or kwargs.get("id")

        if not item_pattern:
            for key in ("title", "item", "name", "task", "todo", "description"):
                val = kwargs.get(key)
                if val:
                    item_pattern = val
                    break

        if not item_pattern and not todo_id:
            return {
                "success": False,
                "error": "Missing todo_id or item_pattern param. Use todo_id from add_todo_item.",
            }

        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)
            session_id = self._session_id()

            success = await todo_manager.mark_todo_completed(
                item_pattern=item_pattern or "", todo_id=todo_id, session_id=session_id
            )

            if success:
                match_info = f"[#{todo_id}]" if todo_id else item_pattern
                result = {
                    "success": True,
                    "message": f"Marked todo complete: {match_info}",
                    "todo_id": todo_id,
                    "item_pattern": item_pattern,
                }
                print(f"✅ {result['message']}")
                return result
            else:
                match_info = f"[#{todo_id}]" if todo_id else item_pattern
                result = {
                    "success": False,
                    "error": f"No matching todo item found: {match_info}",
                }
                print(f"⚠️  {result['error']}")
                return result

        except Exception as e:
            return {"success": False, "error": f"Error marking todo complete: {str(e)}"}

    async def update_todo_item(
        self, old_pattern: str, new_item: str, **kwargs
    ) -> Dict[str, Any]:
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)
            session_id = self._session_id()

            success = await todo_manager.update_todo_item(old_pattern, new_item,
                                                          session_id=session_id)

            if success:
                return {
                    "success": True,
                    "message": f"Todo item updated: {old_pattern} -> {new_item}",
                    "old_pattern": old_pattern,
                    "new_item": new_item,
                }
            else:
                return {
                    "success": False,
                    "error": f"No matching todo item found: {old_pattern}",
                }

        except Exception as e:
            return {"success": False, "error": f"Error updating todo item: {str(e)}"}

    async def get_todo_summary(self, **kwargs) -> Dict[str, Any]:
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)
            session_id = self._session_id()

            summary = await todo_manager.get_todo_summary(session_id=session_id)

            return {"success": "error" not in summary, **summary}

        except Exception as e:
            return {"success": False, "error": f"Error getting todo summary: {str(e)}"}

    async def list_todo_files(self) -> Dict[str, Any]:
        try:
            from ..utils.todo_manager import get_todo_manager

            todo_manager = get_todo_manager(self.project_path)

            files = await todo_manager.list_todo_files()

            return {"success": True, "files": files, "count": len(files)}

        except Exception as e:
            return {"success": False, "error": f"Error listing todo files: {str(e)}"}

    async def add_execution_record(
        self, record: str = None, description: str = None, **kwargs
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "Execution records have been merged into the log system",
        }
