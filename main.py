# 主入口
# main.py
# !/usr/bin/env python3
"""
AI编码助手主入口
基于文件化上下文和分层工具系统的轻量化ReAct架构
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from aacode.core.main_agent import MainAgent
    from aacode.utils.context_manager import ContextManager
    from aacode.utils.safety import SafetyGuard
    from aacode.config import settings
else:
    from .core.main_agent import MainAgent
    from .utils.context_manager import ContextManager
    from .utils.safety import SafetyGuard
    from .config import settings

from aacode.i18n import t


class AICoder:
    """AI编码助手主类"""

    def __init__(
        self,
        project_path: str,
        model_config: Optional[Dict] = None,
        target_project: Optional[str] = None,
    ):
        """
        initializedAI编码助手

        Args:
            project_path: aacode工作目录（存放日志、上下文等）
            model_config: 模型配置
            target_project:  user的实际项目目录（可选，如果指定则工具操作在此目录）
        """
        self.project_path = Path(project_path).absolute()

        # 如果指定了目标项目，使 with 目标项目作为工作目录
        if target_project:
            self.target_project = Path(target_project).absolute()
            if not self.target_project.exists():
                raise ValueError(f"Target project directory does not exist: {self.target_project}")
            print(t("cli.target_project", path=self.target_project))
        else:
            self.target_project = self.project_path
            print(t("cli.work_dir", path=self.project_path))

        # 检查并创建项目目录，处理权限问题
        try:
            self.project_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            print(f"❌ Permission error: cannot create dir '{self.project_path}'")
            print(f"   Error info: {e}")
            print(f"   Check directory permissions or use a writable dir")
            raise

        # 检查目录写入权限
        test_file = self.project_path / ".permission_test"
        try:
            test_file.touch()
            test_file.unlink()
        except PermissionError as e:
            print(f"❌ Permission error: no write access to '{self.project_path}'")
            print(f"   Error info: {e}")
            print(f"   Use 'chmod'  to modify permissions or choose another dir")
            raise

        # 不使 with chdir，避免路径混乱问题
        # 所有工具都会使 with target_project作为基准路径

        # initialized核心组件（使 with target_project作为安全护栏的基准）
        self.safety_guard = SafetyGuard(
            self.target_project,
            dangerous_command_action=settings.safety.dangerous_command_action,
        )
        # 上下文管理器使 with aacode工作目录（存放日志等）
        self.context_manager = ContextManager(self.project_path)
        # 主Agent使 with 目标项目目录（实际操作目录）
        self.main_agent = MainAgent(
            project_path=self.target_project,
            context_manager=self.context_manager,
            safety_guard=self.safety_guard,
            model_config=model_config or settings.DEFAULT_MODEL,
        )

        # 加载项目initialized指令
        self._load_init_instructions()

        # initialized类方法映射器
        self._init_class_method_mapper()

    def _load_init_instructions(self):
        """加载项目initialized指令"""
        # 优先从目标项目加载init.md，如果不存在则从工作目录加载
        init_file = self.target_project / "init.md"
        if not init_file.exists():
            init_file = self.project_path / "init.md"
        if not init_file.exists():
            # 创建默认指令
            default_init = """# Project Guidelines

## Core Rules
1. Annotate path at top of each code file: `# {relative_path}`
2. Prefer modifying existing files over creating new ones
3. All file operations must stay within the project directory
4. Dangerous commands require user confirmation

## Workflow
1. Analyze requirements first, then plan
2. Small steps, frequent testing
3. Write self-contained test functions
4. Check safety before using tools

## Code Quality
- Follow PEP 8 / language best practices
- Keep functions reasonably short (under ~60 lines)
- Add necessary docstrings
- Handle errors gracefully
------
"""
            init_file.write_text(default_init)

        self.init_instructions = init_file.read_text()

    def _init_class_method_mapper(self):
        """initialized类方法映射器"""
        try:
            # 尝试使 with 增强版映射器（现在在class_method_mapper.py中）
            if __package__ in (None, ""):
                from utils.class_method_mapper import EnhancedClassMethodMapper
            else:
                from .utils.class_method_mapper import EnhancedClassMethodMapper

            self.class_method_mapper = EnhancedClassMethodMapper(self.target_project)
            print(t("cli.mapper_init_ok"))
        except ImportError as e:
            print(t("cli.mapper_init_fail", e=str(e)))
            try:
                # 回退到基础版映射器
                if __package__ in (None, ""):
                    from utils.class_method_mapper import ClassMethodMapper
                else:
                    from .utils.class_method_mapper import ClassMethodMapper

                self.class_method_mapper = ClassMethodMapper(self.target_project)
                print(t("cli.mapper_basic_ok"))
            except ImportError as e2:
                print(t("cli.mapper_basic_fail", e=str(e2)))
                self.class_method_mapper = None

        # initializedto-do-list管理器（使 with aacode工作目录）
        if __package__ in (None, ""):
            from utils.todo_manager import get_todo_manager
        else:
            from .utils.todo_manager import get_todo_manager

        self.todo_manager = get_todo_manager(self.project_path)

    def analyze_project_structure(self) -> str:
        """分析项目结构并生成类方法映射"""
        if not self.class_method_mapper:
            return "Class mapper not initialized"

        try:
            print(t("cli.analyze_start"))
            summary = self.class_method_mapper.analyze_project()

            # 尝试使 with 增强版方法
            try:
                # 增强版映射器
                map_file = self.class_method_mapper.save_enhanced_map()
                # Get 语言摘要  for提示
                language_summary = self.class_method_mapper.get_language_summary()

                print(f"✅ Project analysis complete:")
                if "multi_lang_analysis" in summary:
                    lang_stats = summary["multi_lang_analysis"]["languages"]
                    for lang, stats in lang_stats.items():
                        print(
                            f"   - {lang}: {stats['file_count']}  files, {stats['total_lines']}  lines"
                        )
                print(f"   - Structure file: {map_file.name}")

                # 返回前2000字符的摘要（包含最有价值的信息）
                map_content = map_file.read_text(encoding="utf-8")
                # Get 前2000字符作为摘要
                summary_content = map_content[:2000]
                # 如果截断了，添加提示
                if len(map_content) > 2000:
                    summary_content += "...\n\n(Full structure in file, {} chars total)".format(
                        len(map_content)
                    )
                return summary_content

            except AttributeError:
                # 回退到基础版方法
                map_file = self.class_method_mapper.save_class_method_map()
                map_content = map_file.read_text(encoding="utf-8")

                print(f"✅ Python project analysis complete:")
                print(f"   - Classes: {summary.get('class_count', 0)}")
                print(f"   - Functions: {summary.get('function_count', 0)}")
                print(f"   - Files: {summary.get('file_count', 0)}")
                print(f"   - Mapper file: {map_file.name}")

                return map_content[:2000]  # Return first 2000 chars as summary

        except Exception as e:
            error_msg = f"Project structure analysis failed: {e}"
            print(f"❌ {error_msg}")
            return error_msg

    def update_class_method_map(
        self, changed_files: Optional[List[Path]] = None
    ) -> str:
        """更新类方法映射"""
        if not self.class_method_mapper:
            return "Class mapper not initialized"

        try:
            print("🔄 Updating class method mapping...")
            # 处理None情况
            files_to_update = changed_files if changed_files is not None else []

            # 将字符串转换为Path对象（相对路径转换为绝对路径）
            files_to_update = [
                (self.project_path / f) if isinstance(f, str) else f
                for f in files_to_update
            ]

            # 尝试使 with 增强版方法
            try:
                success = self.class_method_mapper.update_analysis(files_to_update)
                map_file = self.project_path / "project_structure.md"
            except AttributeError:
                # 回退到基础版方法
                success = self.class_method_mapper.update_class_method_map(
                    files_to_update
                )
                map_file = self.project_path / "class_method_map.md"

            if success:
                if map_file.exists():
                    map_content = map_file.read_text(encoding="utf-8")
                    return f"Class map updated\n\n{map_content[:1000]}..."
                else:
                    return "Class map update failed: file not generated"
            else:
                return "Class map update failed"

        except Exception as e:
            error_msg = f"Failed to update class method mapping: {e}"
            print(f"❌ {error_msg}")
            return error_msg

    async def run(self, task: str, max_iterations: int = 30) -> Dict[str, Any]:
        """
        execute任务

        Args:
            task: 任务描述
            max_iterations: 最大迭代次数

        Returns:
            execute结果
        """
        print(f"\n🎯 Starting task: {task}")
        print(t("cli.aacode_work_dir", path=self.project_path))
        print(f"🎯 Target project dir: {self.target_project}")
        print(f"📝 Init instructions loaded ({len(self.init_instructions.split())} chars)")

        # 任务开始前分析项目结构
        print(t("cli.analyze_pre_task"))
        analysis_result = self.analyze_project_structure()
        if "failed" not in analysis_result.lower():
            print("✅ Project analysis complete, class-method map generated")
        else:
            print("⚠️  Project analysis incomplete, but task will continue")

        # 创建任务目录
        task_dir = (
            self.project_path
            / ".aacode"
            / f"task_{int(asyncio.get_event_loop().time())}"
        )
        task_dir.mkdir(parents=True, exist_ok=True)

        # 创建to-do-list，并同步到上下文管理器
        print("\n📋 Creating task todo list...")
        todo_file = await self.todo_manager.create_todo_list(
            task, context_manager=self.context_manager
        )
        print(f"✅ Todo created: {todo_file}")

        try:
            # Run主Agent，传递类方法映射信息
            result = await self.main_agent.execute(
                task=task,
                init_instructions=self.init_instructions,
                task_dir=task_dir,
                max_iterations=max_iterations,
                project_analysis=analysis_result,
                todo_manager=self.todo_manager,  # 传递todo管理器
            )
            return result
        except asyncio.CancelledError:
            # 异步任务被取消
            print("\n⏹️ Task cancelled")
            return {
                "status": "cancelled",
                "error": "task cancelled by user",
                "iterations": 0,
                "execution_time": 0,
                "session_id": f"cancelled_{int(asyncio.get_event_loop().time())}",
            }
        except Exception as e:
            # 捕获并处理异常，避免程序崩溃
            print(f"\n❌ Task execution failed: {e}")
            import traceback

            traceback.print_exc()
            # 返回一个包含错误信息的结果，而不是抛出异常
            return {
                "status": "error",
                "error": str(e),
                "iterations": 0,
                "execution_time": 0,
                "session_id": f"error_{int(asyncio.get_event_loop().time())}",
            }
        finally:
            # 确保资源被清理
            try:
                # 清理web_tools资源
                if hasattr(self.main_agent, "web_tools"):
                    await self.main_agent.web_tools.cleanup()
            except Exception as e:
                print(f"⚠️  Error cleaning up: {e}")


async def continue_session(coder, project_dir):
    """Continue session，execute追加任务"""
    print("\n" + "=" * 50)
    print("🔁 Continue session mode")
    print("=" * 50)

    # 检查是否有todo list
    todo_dir = project_dir / ".aacode" / "todos"
    if todo_dir.exists():
        todo_files = list(todo_dir.glob("*.md"))
        if todo_files:
            print(f"\n📋 Found {len(todo_files)} todo lists:")
            for i, todo_file in enumerate(todo_files[-3:], 1):  # 显示最近3个
                print(f"  {i}. {todo_file.name}")
            print("💡 Type 'todo' to view todo list details")

    # 检查是否有session logs
    log_dir = project_dir / ".aacode" / "logs"
    if log_dir.exists():
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            print(f"📝 Found {len(log_files)} session logs")

    while True:
        try:
            print("\nCurrent project dir:", project_dir)
            print("Available commands:")
            print("  - Enter task description to continue")
            print("  - Type 'list' to view project files")
            print("  - Type 'todo' to view todo list")
            print("  - Type 'logs' to view session logs")
            print("  - Type 'exit' or 'quit' to exit")
            print("  - Type 'clear' to clear project dir")
            print("  - Type 'continue' for resume help")
            print("  - Type 'help' for help")

            user_input = input("\n> ").strip()

            if user_input.lower() in ["exit", "quit", "q"]:
                print("👋 Exiting session")
                break
            elif user_input.lower() == "list":
                # 列出项目文件
                print("\n📁 Project files:")
                files = list(project_dir.glob("*"))
                if not files:
                    print("  (empty directory)")
                else:
                    for file in files:
                        if file.is_file():
                            size = file.stat().st_size
                            print(f"  - {file.name} ({size} bytes)")
                continue
            elif user_input.lower() == "todo":
                # 查看todo list
                if todo_dir.exists():
                    todo_files = list(todo_dir.glob("*.md"))
                    if todo_files:
                        print("\n📋 todo list:")
                        for i, todo_file in enumerate(todo_files, 1):
                            with open(todo_file, "r", encoding="utf-8") as f:
                                first_line = f.readline().strip()
                            print(f"  {i}. {todo_file.name}")
                            print(f"     Content: {first_line[:80]}...")
                        print("\n💡 Enter todo list number to view details, or enter 'back' to go back")
                        choice = input("Select todo list (number/back): ").strip()
                        if choice.lower() != "back" and choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(todo_files):
                                with open(todo_files[idx], "r", encoding="utf-8") as f:
                                    print(f"\n📄 {todo_files[idx].name}:")
                                    print(f.read())
                    else:
                        print("📭 No todo lists")
                else:
                    print("📭 Todo directory does not exist")
                continue
            elif user_input.lower() == "logs":
                # 查看session logs
                if log_dir.exists():
                    log_files = list(log_dir.glob("*.log"))
                    if log_files:
                        print("\n📝 session logs:")
                        for i, log_file in enumerate(log_files[-5:], 1):  # 显示最近5个
                            size = log_file.stat().st_size
                            print(f"  {i}. {log_file.name} ({size} bytes)")
                        print("\n💡 Enter log number to view last few lines, or enter 'back' to go back")
                        choice = input("Select log (number/back): ").strip()
                        if choice.lower() != "back" and choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(log_files):
                                with open(log_files[idx], "r", encoding="utf-8") as f:
                                    lines = f.readlines()
                                    print(f"\n📄 {log_files[idx].name} (last 20 lines):")
                                    for line in lines[-20:]:
                                        print(line.rstrip())
                    else:
                        print("📭 No session logs")
                else:
                    print("📭 Log directory does not exist")
                continue
            elif user_input.lower() == "clear":
                # 确认清空项目
                confirm = (
                    input("⚠️  Confirm clearing project directory? (type 'yes' to confirm): ").strip().lower()
                )
                if confirm == "yes":
                    for file in project_dir.glob("*"):
                        if file.is_file() and file.name != ".env":
                            file.unlink()
                    print("✅ Project directory cleared")
                continue
            elif user_input.lower() in ["continue"]:
                # 处理"继续"命令
                print("\n" + "=" * 50)
                print("🔄 Resume task instructions")
                print("=" * 50)
                print("\nTo resume a previously interrupted task, here are several methods:")
                print("\n1. 🎯 Enter a specific task description")
                print("   Example: 'Complete user registration feature'")
                print("   System will auto-reference previous todo list")
                print("\n2. 🔄 Resume using session ID")
                print("   When re-running, use: --session <session_id>")
                print("   Session ID is displayed when task starts")
                print("   Example: python main.py --session session_20260212_123548_3")
                print("\n3. 📋 Continue based on todo list")
                print("   Type 'todo' to view existing todo lists")
                print("   After selecting a todo list, enter a relevant task description")
                print("\n4. 🔍 Check project status")
                print("   Type 'list' to view project files")
                print("   Type 'logs' to view session logs")
                print("\n💡 Tip: Entering a specific task description is the most direct approach")
                continue
            elif user_input.lower() == "help":
                print("\n" + "=" * 50)
                print("📚 Help Documentation")
                print("=" * 50)
                print("\n🔧 Common Commands:")
                print("  list    - to view project files")
                print("  todo    - to view todo lists")
                print("  logs    - to view session logs")
                print("  clear   - to clear project dir")
                print("  exit    - to exit session")
                print("  help    - to show help")
                print("\n🎯 Task Execution:")
                print("  Enter a task description to start working")
                print("  Example: 'Add user login feature'")
                print("  System will automatically analyze the project and make a plan")
                print("\n🔄 Resume Task:")
                print("  Type 'continue' for resume help")
                print("  Or enter task description to continue")
                print("\n⚠️  Notes:")
                print("  1. Ensure API key is properly configured")
                print("  2. Large projects may take longer")
                print("  3. Use Ctrl+C to interrupt current task")
                print("  4. After interruption, type 'y' to continue session")
                continue
            elif user_input:
                # 检查是否是"继续任务"或类似命令
                if user_input.lower() in ["continue task", "continue previous task", "resume task"]:
                    # Trying to resume recent task
                    print(f"\n🔄 Trying to resume recent task...")

                    # 检查todo list目录
                    todo_dir = project_dir / ".aacode" / "todos"
                    if todo_dir.exists():
                        todo_files = list(todo_dir.glob("*.md"))
                        if todo_files:
                            # Get 最新的todo list
                            latest_todo = max(
                                todo_files, key=lambda f: f.stat().st_mtime
                            )
                            print(f"📋 Found todo: {latest_todo.name}")

                            # 读取todo list内容
                            with open(latest_todo, "r", encoding="utf-8") as f:
                                todo_content = f.read()

                            # 提取任务描述
                            import re

                            task_match = re.search(r"\*\*Task\*\*: (.+)", todo_content)
                            if task_match:
                                original_task = task_match.group(1)
                                print(f"🎯 Original task: {original_task}")

                                # 询问 user是否继续这个任务
                                confirm = (
                                    input(f"Continue this task? (y/n): ").strip().lower()
                                )
                                if confirm == "y":
                                    user_input = original_task
                                    print(f"🔄 Continue task: {original_task}")
                                else:
                                    print("Enter new task description:")
                                    user_input = input("> ").strip()
                            else:
                                print("❌ Unable to extract task description from todo list")
                                print("Enter task description:")
                                user_input = input("> ").strip()
                        else:
                            print("📭 No todo lists found")
                            print("Enter task description:")
                            user_input = input("> ").strip()
                    else:
                        print("📭 Todo directory does not exist")
                        print("Enter task description:")
                        user_input = input("> ").strip()

                # execute task
                print(f"\n🎯 Starting execution: {user_input}")
                print("Preparing...")

                try:
                    result = await coder.run(user_input)

                    # 检查任务是否成功
                    if result.get("status") == "error":
                        print(f"\n❌ Task execution failed: {result.get('error', 'unknown error')}")
                        print("💡 Tip: check error info, or enter a new task to retry")
                    else:
                        print(f"\n✅ Task complete!")
                        print(f"Iterations: {result.get('iterations', 0)}")
                        print(f"Execution time: {result.get('execution_time', 0):.2f}s")

                        # 显示会话ID以便后续恢复
                        session_id = result.get("session_id")
                        if session_id and not session_id.startswith("error_"):
                            print(f"Session ID: {session_id}")
                            print(f"Use --session {session_id} to continue this session")
                except Exception as e:
                    print(f"\n❌ Task execution failed: {e}")
                    print("💡 Tip: Check error messages, or enter a new task to retry")

                continue
            else:
                print("❌ Please enter a valid command")

        except KeyboardInterrupt:
            print("\n\n⏸️  Session interrupted")
            print("Enter 'y' to continue current session, or 'n' to exit")
            choice = input("Continue? (y/n): ").strip().lower()
            if choice == "y":
                continue
            else:
                print("👋 Exit")
                break
        except Exception as e:
            print(f"\n❌ Execution error: {e}")
            import traceback

            traceback.print_exc()
            print("\n💡 Tip: Check error messages, or enter a new task to retry")
            print("   Type 'help' for documentation")


async def main():
    """命令 lines主函数"""
    import time as time_module

    parser = argparse.ArgumentParser(
        description="🤖 AI Coding Assistant - supports continuous dialogue and intelligent planning",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--project",
        default=f"projects/my_project_{int(time_module.time())}",
        help="aacode workspace directory (stores logs, context, etc.), defaults to projects directory",
    )
    parser.add_argument(
        "-t",
        "--target",
        help="Target project directory (user's actual project path). If not specified, uses --project directory",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help='Task description, e.g. "create a simple Flask app". If first argument is a path, it is used as target project',
    )
    parser.add_argument("--continue", action="store_true", help="Continue previous session")
    parser.add_argument("--session", help="Specify session ID")
    parser.add_argument("--plan-first", action="store_true", help="Plan-first execution mode")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    # 加载环境变量配置
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

    # 解析任务和目标项目
    # 如果第一个参数是路径（存在的目录），则作为目标项目
    target_project = args.target
    task_parts = args.task

    if task_parts and not target_project:
        first_arg = task_parts[0]
        # 检查第一个参数是否是存在的目录
        # 添加长度检查，避免把长任务描述当作路径
        if len(first_arg) < 200 and Path(first_arg).is_dir():
            target_project = first_arg
            task_parts = task_parts[1:]  # 剩余部分作为任务
            print(f"🎯 Detected target project: {target_project}")

    # 如果命令 lines没给任务，就交互式询问
    task = " ".join(task_parts).strip()
    if not task:
        task = input("Enter task: ").strip()

    # 创建AI编码助手实例
    coder = AICoder(args.project, target_project=target_project)

    # Run任务
    try:
        result = await coder.run(task)

        print(f"\n✅ Task complete!")
        print(f"📋 Session ID: {result.get('session_id', 'N/A')}")
        print(f"Iterations: {result.get('iterations', 0)}")
        print(f"Final status: {result.get('status', 'unknown')}")
        print(f"Execution time: {result.get('execution_time', 0):.2f}s")

        # 检查生成的文件
        project_dir = Path(args.project)
        created_files = []

        # 递归查找项目目录下的Python文件（排除.aacode和虚拟环境）
        exclude_dirs = {
            ".aacode",
            ".venv",
            "venv",
            "__pycache__",
            ".git",
            "node_modules",
        }

        for py_file in project_dir.rglob("*.py"):
            # 排除特定目录和主程序
            if py_file.name != "main.py" and not any(
                excluded in py_file.parts for excluded in exclude_dirs
            ):
                # 检查文件是否是最近创建的（5分钟内）
                import time

                if time.time() - py_file.stat().st_mtime < 300:  # 5分钟 = 300秒
                    created_files.append(py_file)
        """
        # 这个后续动作有点生硬，先注释
        if created_files:
            print("\n📁 Generated files:")
            for file in created_files:
                # 显示相对路径
                rel_path = file.relative_to(project_dir)
                print(f"  - {rel_path}")
                
                # 询问RunPython文件
                try:
                    response = input(f"Run {rel_path}? (y/n): ").strip().lower()
                    if response == 'y':
                        print(f"🚀 Run {rel_path}:")
                        
                        # Method 1: 尝试使 with 项目根目录作为工作目录
                        result = subprocess.run([sys.executable, str(rel_path)], 
                                              cwd=project_dir, 
                                              capture_output=True, text=True,
                                              env={**os.environ, 'PYTHONPATH': str(project_dir)})
                        
                        if result.returncode == 0:
                            print(f"✅ Output: {result.stdout.strip()}")
                        else:
                            error_msg = result.stderr.strip()
                            print(f"❌ Error: {error_msg}")
                            
                            # 提供更详细的错误信息和解决建议
                            if error_msg:
                                print(f"\n💡 Analysis:")
                                if "No module named" in error_msg:
                                    print(f"   - Import error: missing dependency module")
                                    print(f"   - Suggestion: check if dependencies need installing")
                                    print(f"   - Or: file may need to run in specific directory")
                                elif "FileNotFoundError" in error_msg or "No such file" in error_msg:
                                    print(f"   - File path error")
                                    print(f"   - Tip: check relative paths used in the file")
                                else:
                                    print(f"   - Tip: check code logic and syntax")
                except (KeyboardInterrupt, EOFError):
                    print("\nSkipping run")
                    break
        """

        # 任务完成后，默认进入Continue session模式
        print("\n" + "=" * 50)
        print("✅ Task completed!")
        print("=" * 50)

        # 询问是否继续execute追加任务
        try:
            response = (
                input("\n🔁 Continue with other tasks? (y/n, default y): ").strip().lower()
            )
            if not response or response == "y":
                await continue_session(coder, project_dir)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exit")

    except KeyboardInterrupt:
        print("\n⏹️  User interrupted")
        # 即使中断，也询问是否继续
        try:
            response = (
                input("\n🔁 Task interrupted. Continue with other tasks? (y/n): ").strip().lower()
            )
            if response == "y":
                project_dir = Path(args.project)
                await continue_session(coder, project_dir)
        except:
            pass
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        # 错误后也询问是否继续
        try:
            response = (
                input("\n🔁 Error occurred. Continue with other tasks? (y/n): ").strip().lower()
            )
            if response == "y":
                project_dir = Path(args.project)
                await continue_session(coder, project_dir)
        except:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Program interrupted by user, exiting normally")
        sys.exit(0)
