# Runner module for executing AICoder tasks
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional


class AICoderRunner:
    """Runner for executing AICoder tasks with streaming output"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).absolute()
        self.project_path.mkdir(parents=True, exist_ok=True)
        self.running_task = None
        self._cleanup_done = False

    async def run_task_stream(
        self,
        task: str,
        target_project: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run a task and yield events for streaming"""
        if target_project:
            work_dir = Path(target_project).absolute()
        else:
            work_dir = self.project_path

        os.environ["AACODE_WORK_DIR"] = str(self.project_path)

        yield {"type": "start", "task": task, "project": str(work_dir)}

        try:
            if __package__ in (None, ""):
                from aacode.core.main_agent import MainAgent
                from aacode.utils.context_manager import ContextManager
                from aacode.utils.safety import SafetyGuard
                from aacode.config import settings
            else:
                from aacode.core.main_agent import MainAgent
                from aacode.utils.context_manager import ContextManager
                from aacode.utils.safety import SafetyGuard
                from aacode.config import settings

            safety_guard = SafetyGuard(work_dir)
            context_manager = ContextManager(self.project_path)

            agent = MainAgent(
                project_path=work_dir,
                context_manager=context_manager,
                safety_guard=safety_guard,
                model_config=settings.DEFAULT_MODEL,
            )

            if session_id:
                await agent.session_manager.switch_session(session_id)
                yield {"type": "session_switched", "session_id": session_id}
            else:
                session_id = await agent.session_manager.create_session(task)
                yield {"type": "session_created", "session_id": session_id}

            self.running_task = asyncio.current_task()

            result = await agent.run(task)

            if result.get("success"):
                yield {"type": "done", "session_id": session_id, "result": result}
            else:
                yield {"type": "error", "message": result.get("error", "Unknown error")}

        except Exception as e:
            yield {"type": "error", "message": str(e)}

    async def validate_api_key(
        self, api_key: str, model: str = "deepseek-chat", base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate API key with a simple request"""
        import openai

        os.environ["LLM_API_KEY"] = api_key
        if base_url:
            os.environ["LLM_API_URL"] = base_url
        os.environ["LLM_MODEL_NAME"] = model

        try:
            if base_url:
                client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
            else:
                client = openai.AsyncOpenAI(api_key=api_key)

            try:
                await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "Hi"}],
                        max_tokens=10,
                    ),
                    timeout=10.0,
                )
                return {"valid": True}
            except asyncio.TimeoutError:
                return {"valid": False, "error": "Request timeout"}
            except Exception as e:
                error_msg = str(e).lower()
                if (
                    "api" in error_msg
                    or "key" in error_msg
                    or "auth" in error_msg
                    or "invalid" in error_msg
                ):
                    return {"valid": False, "error": "Invalid API key or model"}
                return {"valid": False, "error": str(e)}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def get_session_list(self, project_path: str) -> list:
        """Get list of sessions for a project"""
        session_path = (
            Path(project_path) / ".aacode" / "sessions" / "sessions_index.json"
        )
        if not session_path.exists():
            return []

        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                sessions = []
                for session_id, info in data.items():
                    sessions.append(
                        {
                            "session_id": session_id,
                            "title": info.get("title", ""),
                            "created_at": info.get("created_at", 0),
                            "last_activity": info.get("last_activity", 0),
                            "status": info.get("status", "active"),
                        }
                    )
                sessions.sort(key=lambda x: x.get("last_activity", 0), reverse=True)
                return sessions
        except Exception:
            return []

    async def get_session_messages(self, project_path: str, session_id: str) -> list:
        """Get messages for a session"""
        session_file = (
            Path(project_path) / ".aacode" / "sessions" / f"{session_id}.json"
        )
        if not session_file.exists():
            return []

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("messages", [])
        except Exception:
            return []

    async def cleanup(self):
        """Cleanup resources"""
        if not self._cleanup_done:
            self._cleanup_done = True
            if self.running_task and not self.running_task.done():
                self.running_task.cancel()
                try:
                    await self.running_task
                except asyncio.CancelledError:
                    pass
