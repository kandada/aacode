# To-Do List管理器
# utils/todo_manager.py
"""
To-Do List管理器
负责创建、更新和跟踪任务待办清单
支持按 session_id 隔离多个会话的待办清单
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiofiles
import json
import re
from aacode.i18n import t
from aacode.utils.file_lock import file_lock


class TodoManager:
    """To-Do List管理器，支持按 session_id 隔离多个会话"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.todo_dir = project_path / ".aacode" / "todos"
        self.todo_dir.mkdir(parents=True, exist_ok=True)
        self.current_todo_file: Optional[Path] = None
        self.todos: List[Dict] = []
        self.todo_counter: int = 0
        self._session_todo_files: Dict[str, Path] = {}
        self._session_counters: Dict[str, int] = {}
        self._removed_sessions: set = set()
        self._todo_counter_atomic: int = 0
        self._load_session_todo_map()

    def _session_map_path(self) -> Path:
        return self.todo_dir / "session_todo_map.json"

    def _load_session_todo_map(self):
        map_file = self._session_map_path()
        if map_file.exists():
            try:
                with open(map_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, rel_path in data.get("sessions", {}).items():
                    abs_path = self.project_path / rel_path
                    if abs_path.exists():
                        self._session_todo_files[sid] = abs_path
                self._session_counters = data.get("counters", {})
                self._removed_sessions = set(data.get("removed", []))
            except Exception:
                pass

    def _save_session_todo_map(self):
        map_file = self._session_map_path()
        try:
            data = {
                "sessions": {
                    sid: str(fp.relative_to(self.project_path))
                    for sid, fp in self._session_todo_files.items()
                    if fp.exists()
                },
                "counters": self._session_counters,
                "removed": list(self._removed_sessions),
            }
            map_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _resolve_todo_file(self, session_id: Optional[str] = None) -> Optional[Path]:
        if session_id and session_id in self._session_todo_files:
            f = self._session_todo_files[session_id]
            if f.exists():
                return f
        if session_id and session_id not in self._removed_sessions:
            found = self._find_session_todo_from_disk(session_id)
            if found:
                self._session_todo_files[session_id] = found
                return found
        if session_id:
            return None
        return self.current_todo_file

    def _resolve_counter(self, session_id: Optional[str] = None) -> int:
        if session_id and session_id in self._session_counters:
            return self._session_counters[session_id]
        return self.todo_counter

    def _set_counter(self, value: int, session_id: Optional[str] = None):
        if session_id:
            self._session_counters[session_id] = value
        else:
            self.todo_counter = value

    def _find_session_todo_from_disk(self, session_id: str) -> Optional[Path]:
        for f in sorted(self.todo_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.name == "session_todo_map.json":
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if f"**Session**: {session_id}" in content:
                    return f
            except Exception:
                pass
        return None

    def set_session_todo(self, session_id: str, todo_file_path: Path):
        self._session_todo_files[session_id] = todo_file_path
        self._session_counters[session_id] = 0
        self._save_session_todo_map()

    async def create_todo_list(
        self,
        task_description: str,
        project_name: Optional[str] = None,
        context_manager: Any = None,
        session_id: Optional[str] = None,
    ) -> str:
        if project_name is None:
            project_name = self.project_path.name
            if not project_name or project_name == ".":
                project_name = "project"

        clean_project_name = re.sub(r"[^\w\-_]", "_", project_name)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._todo_counter_atomic += 1
        filename = f"{clean_project_name}_to-do-list_{timestamp}_{self._todo_counter_atomic:04d}.md"
        self.current_todo_file = self.todo_dir / filename

        if session_id:
            self._session_todo_files[session_id] = self.current_todo_file
            self._session_counters[session_id] = 0
            self._save_session_todo_map()

        if context_manager:
            context_manager.current_todo_file = self.current_todo_file

        self.todo_counter = 0

        session_header = f"\n**Session**: {session_id}" if session_id else ""

        todo_content = f"""# {clean_project_name} - Todo List

**Task**: {task_description}
**Created**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{session_header}

## Todo

## Completed
"""

        try:
            async with aiofiles.open(
                self.current_todo_file, "w", encoding="utf-8"
            ) as f:
                await f.write(todo_content)
        except asyncio.CancelledError:
            return ""
        except Exception as e:
            print(f"⚠️  Failed to create todo list: {e}")
            return ""

        print(f"📋 Created todo list: {self.current_todo_file.name}")
        return str(self.current_todo_file.relative_to(self.project_path))

    async def add_todo_item(
        self, item: str, priority: str = "medium", category: str = "Task",
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        todo_file = self._resolve_todo_file(session_id)
        if not todo_file or not todo_file.exists():
            print("⚠️  No active todo list file")
            return None

        try:
            with file_lock(todo_file):
                async with aiofiles.open(todo_file, "r", encoding="utf-8") as f:
                    content = await f.read()

                counter = self._resolve_counter(session_id)
                if counter == 0:
                    counter = self._load_counter_from_content(content)
                    self._set_counter(counter, session_id)

                lines = content.split("\n")
                insert_pos = -1
                for i, line in enumerate(lines):
                    if line.strip() == "## Todo":
                        insert_pos = i + 1
                        break

                if insert_pos == -1:
                    print("⚠️  Todo section not found")
                    return None

                counter += 1
                self._set_counter(counter, session_id)
                todo_id = f"t{counter}"

                priority_mark = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    priority, ""
                )
                new_item = f"- [ ] {priority_mark} **{category}** [#{todo_id}]: {item}"
                lines.insert(insert_pos, new_item)

                async with aiofiles.open(todo_file, "w", encoding="utf-8") as f:
                    await f.write("\n".join(lines))

                if session_id:
                    self._save_session_todo_map()

                return todo_id
        except Exception as e:
            print(f"⚠️  Failed to add todo: {e}")
            return None

    def _load_counter_from_content(self, content: str) -> int:
        matches = re.findall(r'\[#t(\d+)\]', content)
        if matches:
            return max(int(n) for n in matches)
        return 0

    def _load_counter(self, content: str) -> None:
        self.todo_counter = self._load_counter_from_content(content)

    async def mark_todo_completed(self, item_pattern: str = "", todo_id: Optional[str] = None,
                                   session_id: Optional[str] = None) -> bool:
        todo_file = self._resolve_todo_file(session_id)
        if not todo_file:
            print("⚠️  No active todo list file")
            return False

        with file_lock(todo_file):
            async with aiofiles.open(todo_file, "r", encoding="utf-8") as f:
                content = await f.read()

            lines = content.split("\n")
            updated = False

            if todo_id:
                tag = f"[#{todo_id}]"
                for i, line in enumerate(lines):
                    if tag in line:
                        if line.strip().startswith("- [x]"):
                            item_desc = line.replace("- [x]", "").strip()
                            item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*\[#\w+\]:\s*", "", item_desc)
                            print(f"⏭️  [#{todo_id}] already completed: {item_desc[:50]}...")
                            updated = True
                            break
                        if line.strip().startswith("- [ ]"):
                            lines[i] = line.replace("- [ ]", "- [x]", 1)
                            updated = True
                            item_desc = line.replace("- [ ]", "").strip()
                            item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*\[#\w+\]:\s*", "", item_desc)
                            self._add_to_completed_section(lines, item_desc, todo_id)
                            print(f"✅ Marked complete [#{todo_id}]: {item_desc[:50]}...")
                            break

            if not updated and item_pattern:
                pattern_lower = item_pattern.lower()
                for i, line in enumerate(lines):
                    if (
                        line.strip().startswith("- [ ]")
                        and pattern_lower in line.lower()
                    ):
                        lines[i] = line.replace("- [ ]", "- [x]", 1)
                        updated = True
                        id_match = re.search(r'\[#(t\d+)\]', line)
                        matched_id = id_match.group(1) if id_match else None
                        item_desc = line.replace("- [ ]", "").strip()
                        item_desc = re.sub(r"^[🔴🟡🟢]\s*\*\*.*?\*\*\s*(\[#\w+\]:\s*)?", "", item_desc)
                        self._add_to_completed_section(lines, item_desc, matched_id)
                        print(f"✅ Marked complete: {item_desc[:50]}...")

            if not updated and item_pattern:
                pattern_lower = item_pattern.lower()
                stop_words = {"the", "a", "an", "is", "of", "in", "to", "and", "for", "python", "py"}
                raw_words = [w for w in re.split(r'[\s,，。、]+', pattern_lower) if w and len(w) > 1]
                keywords = []
                for w in raw_words:
                    if w in stop_words:
                        continue
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
                                print(f"✅ Fuzzy match marked complete: {item_desc[:50]}...")
                                break

            if updated:
                async with aiofiles.open(todo_file, "w", encoding="utf-8") as f:
                    await f.write("\n".join(lines))

            return updated

    def _add_to_completed_section(self, lines: List[str], item_desc: str, todo_id: Optional[str] = None):
        completed_section_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "## Completed":
                completed_section_start = i
                break

        if completed_section_start == -1:
            return

        insert_position = completed_section_start + 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        id_tag = f" [#{todo_id}]" if todo_id else ""
        new_item = f"- ✅ **{timestamp}**{id_tag}: {item_desc}"
        lines.insert(insert_position, new_item)

    async def update_todo_item(self, old_pattern: str, new_item: str,
                                session_id: Optional[str] = None) -> bool:
        todo_file = self._resolve_todo_file(session_id)
        if not todo_file:
            print("⚠️  No active todo list file")
            return False

        with file_lock(todo_file):
            async with aiofiles.open(todo_file, "r", encoding="utf-8") as f:
                content = await f.read()

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
                    print(f"🔄 Updated todo: {new_item[:50]}...")

            if updated:
                async with aiofiles.open(todo_file, "w", encoding="utf-8") as f:
                    await f.write("\n".join(lines))

            return updated

    async def add_execution_record(self, record: str) -> bool:
        return True

    async def get_todo_summary(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        todo_file = self._resolve_todo_file(session_id)
        if not todo_file or not todo_file.exists():
            if not session_id:
                files = await self.list_todo_files()
                if files:
                    latest_file = self.todo_dir / files[0]["filename"]
                    self.current_todo_file = latest_file
                    todo_file = latest_file
                else:
                    return {
                        "empty": True,
                        "message": "No todo lists yet, use /newtodo to create a new task",
                    }

        if not todo_file or not todo_file.exists():
            return {
                "empty": True,
                "message": "No todo lists yet, use /newtodo to create a new task",
            }

        try:
            async with aiofiles.open(todo_file, "r", encoding="utf-8") as f:
                content = await f.read()

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

            project_name = "Unknown project"
            for line in lines:
                if line.startswith("# "):
                    project_name = line.replace("# ", "").split(" - ")[0]
                    break

            return {
                "project_name": project_name,
                "todo_file": str(todo_file.relative_to(self.project_path)),
                "total_todos": total_todos,
                "completed_todos": completed_todos,
                "pending_todos": pending_todos,
                "completion_rate": (
                    (completed_todos / total_todos * 100) if total_todos > 0 else 0
                ),
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": f"Failed to read todo list: {str(e)}"}

    async def list_todo_files(self) -> List[Dict[str, Any]]:
        try:
            todo_files = []
            for file_path in self.todo_dir.glob("*.md"):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        first_line = await f.readline()
                        second_line = await f.readline()

                        project_name = "Unknown project"
                        if first_line.startswith("# "):
                            project_name = first_line.replace("# ", "").split(" - ")[0]

                        created_time = "Unknown time"
                        if second_line.startswith("**Created**: "):
                            created_time = second_line.replace("**Created**: ", "").strip()

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

            todo_files.sort(
                key=lambda x: x.get("modified_time", "") or "", reverse=True
            )
            return todo_files
        except Exception as e:
            print(f"⚠️ Failed to list todo files: {e}")
            return []

    async def cleanup_old_todos(self, keep_days: int = 30) -> None:
        try:
            import time

            cutoff_time = time.time() - (keep_days * 24 * 3600)

            for todo_file in self.todo_dir.glob("*.md"):
                if todo_file.stat().st_mtime < cutoff_time:
                    try:
                        todo_file.unlink()
                        print(f"🗑️  Cleaned old todo list: {todo_file.name}")
                    except Exception as e:
                        print(f"⚠️ Failed to clean todo list {todo_file.name}: {e}")
        except Exception as e:
            print(f"⚠️ Todo list cleanup failed: {e}")

    def remove_session_todo(self, session_id: str):
        if session_id in self._session_todo_files:
            del self._session_todo_files[session_id]
        if session_id in self._session_counters:
            del self._session_counters[session_id]
        self._removed_sessions.add(session_id)
        self._save_session_todo_map()


_todo_managers: Dict[str, TodoManager] = {}


def get_todo_manager(project_path: Path) -> TodoManager:
    project_key = str(project_path.absolute())
    if project_key not in _todo_managers:
        _todo_managers[project_key] = TodoManager(project_path)
    return _todo_managers[project_key]
