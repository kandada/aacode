# 上下文管理 - 极简版
# utils/context_manager.py
"""
极简文件化上下文管理器
遵循Cursor动态上下文发现：让AI自己找信息
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    from config import settings
except ImportError:
    from ..config import settings


class ContextManager:
    """极简文件化上下文管理器"""

    def __init__(self, project_path):
        from pathlib import Path
        self.project_path = Path(project_path) if not isinstance(project_path, Path) else project_path
        self.context_dir = self.project_path / ".aacode" / "context"
        self.context_dir.mkdir(parents=True, exist_ok=True)
        # 优化1：待办文件路径始终在上下文中
        self.current_todo_file = None  # 当前待办文件路径

    async def get_context(self) -> str:
        """获取当前上下文 - 增强版，确保关键信息始终存在，增强健壮性"""
        context_parts = []

        # 1. 始终加载 init.md（最高优先级）- 增强错误处理
        init_file = self.project_path / "init.md"
        try:
            if init_file.exists():
                try:
                    init_content = init_file.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    if init_content.strip():
                        context_parts.append(
                            f"# 📋 项目初始化指令 (init.md)\n{init_content[:20000]}"
                        )
                    else:
                        context_parts.append("# 📋 项目初始化指令\n⚠️ init.md 文件为空")
                except UnicodeDecodeError:
                    context_parts.append(
                        "# 📋 项目初始化指令\n⚠️ 文件编码错误，无法读取"
                    )
                except PermissionError:
                    context_parts.append("# 📋 项目初始化指令\n⚠️ 权限不足，无法读取")
                except Exception as e:
                    context_parts.append(
                        f"# 📋 项目初始化指令\n⚠️ 读取失败: {str(e)[:100]}"
                    )
            else:
                context_parts.append(
                    "# 📋 项目初始化指令\n⚠️ init.md 文件不存在，建议创建"
                )
        except Exception as e:
            context_parts.append(f"# 📋 项目初始化指令\n⚠️ 检查文件失败: {str(e)[:100]}")

        # 优化1：待办文件路径始终在上下文中
        if self.current_todo_file:
            try:
                todo_rel_path = self.current_todo_file.relative_to(self.project_path)
                context_parts.append(
                    f"# 📋 当前待办清单\n文件路径: {todo_rel_path}\n提示: 使用待办工具时会自动使用此文件"
                )
            except Exception:
                pass

        # 2. 读取最新的观察结果和观察历史 - 增强错误处理
        observation_file = self.context_dir / "latest_observation.txt"
        history_file = self.context_dir / "observation_history.txt"

        # 读取最新观察
        try:
            if observation_file.exists():
                try:
                    latest_obs = observation_file.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    if latest_obs and latest_obs.strip():
                        # 显示更多观察内容（从500增加到3000字符）
                        context_parts.append(f"## 最新观察\n{latest_obs[:3000]}")
                except Exception:
                    # 静默失败，不影响主流程
                    pass
        except Exception:
            pass

        # 读取观察历史（最近5次）
        try:
            if history_file.exists():
                try:
                    history_content = history_file.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    if history_content and history_content.strip():
                        history_entries = history_content.strip().split("\n---\n")
                        if len(history_entries) > 1:  # 只有最新观察时不需要显示历史
                            # 显示最近3次历史观察（不包括最新）
                            recent_history = (
                                history_entries[-4:-1]
                                if len(history_entries) > 4
                                else history_entries[:-1]
                            )
                            if recent_history:
                                context_parts.append(
                                    f"## 近期观察历史\n"
                                    + "\n---\n".join(recent_history[-3:])
                                )
                except Exception:
                    # 静默失败
                    pass
        except Exception:
            pass

        # 3. 读取重要错误和警告历史 - 增强错误处理
        errors_file = self.context_dir / "important_errors.txt"
        try:
            if errors_file.exists():
                try:
                    errors = errors_file.read_text(encoding="utf-8", errors="ignore")
                    if errors and errors.strip():
                        context_parts.append(
                            f"## ⚠️ 重要错误历史（避免重复）\n{errors[-800:]}"
                        )  # 最近800字符
                except Exception:
                    # 静默失败
                    pass
        except Exception:
            pass

        # 4. 添加项目路径信息
        try:
            context_parts.append(
                f"## 工作目录\n当前工作目录: {self.project_path.absolute()}"
            )
        except Exception:
            context_parts.append(f"## 工作目录\n当前工作目录: {self.project_path}")

        # 5. 添加重要目录信息（包含常用文档路径）- 增强错误处理
        important_dirs = []
        try:
            aacode_dir = self.project_path / ".aacode"
            if aacode_dir.exists() and aacode_dir.is_dir():
                important_dirs.append(f"- .aacode/ (系统目录)")
                for subdir_name in ["context", "todos", "tests", "sandboxes"]:
                    try:
                        subdir = aacode_dir / subdir_name
                        if subdir.exists() and subdir.is_dir():
                            important_dirs.append(f"  - .aacode/{subdir_name}/")
                    except Exception:
                        continue
        except Exception:
            pass

        # 列出常见文档文件 - 增强错误处理
        doc_files = []
        try:
            for pattern in [
                "README*.md",
                "*.txt",
                "requirements.txt",
                "package.json",
                "*.yaml",
                "*.yml",
            ]:
                try:
                    for doc_file in self.project_path.glob(pattern):
                        if doc_file.is_file() and not str(doc_file).startswith(
                            ".aacode"
                        ):
                            doc_files.append(f"  - {doc_file.name}")
                            if len(doc_files) >= 10:  # 限制数量
                                break
                    if len(doc_files) >= 10:
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if doc_files:
            important_dirs.append(f"\n常用文档:")
            important_dirs.extend(doc_files[:10])  # 最多10个

        if important_dirs:
            context_parts.append(f"## 重要目录和文档\n" + "\n".join(important_dirs))

        # 6. 使用bash万能适配器获取项目结构 - 增强错误处理和超时保护
        try:
            # 使用配置的超时时间和文件数量限制
            if __package__ in (None, ""):
                from config import settings
            else:
                from ..config import settings

            file_search_timeout = settings.timeouts.file_search
            max_files = getattr(settings.limits, "max_context_files", 50)
            prioritize = getattr(settings.limits, "prioritize_file_types", True)

            cmd = f"find . -type f \\( -name '*.py' -o -name '*.md' -o -name '*.txt' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.csv' -o -name '*.xlsx' -o -name '*.pdf' \\) | grep -v '.aacode' | head -{max_files}"

            process = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.project_path,
                ),
                timeout=file_search_timeout,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=file_search_timeout
            )

            if process.returncode == 0 and stdout:
                files = stdout.decode(errors="ignore").strip().split("\n")
                file_list = [
                    f[2:] if f.startswith("./") else f for f in files if f.strip()
                ]

                # 智能优先级排序（如果启用）
                if prioritize and file_list:
                    file_list = self._prioritize_files(file_list)

                if file_list:
                    total_files = len(file_list)
                    if total_files >= max_files:
                        context_parts.append(
                            f"## 项目文件结构\n（显示前 {max_files} 个文件，共约 {max_files}+ 个）\n{chr(10).join(file_list)}"
                        )
                    else:
                        context_parts.append(
                            f"## 项目文件结构\n{chr(10).join(file_list)}"
                        )
                else:
                    context_parts.append("## 项目文件结构\n项目目录为空")
            else:
                context_parts.append("## 项目文件结构\n项目目录为空或无法读取")
        except asyncio.TimeoutError:
            context_parts.append("## 项目文件结构\n获取超时，项目可能较大")
        except FileNotFoundError:
            # find命令不可用，尝试使用Python实现
            try:
                if __package__ in (None, ""):
                    from config import settings
                else:
                    from ..config import settings

                max_files = getattr(settings.limits, "max_context_files", 50)
                prioritize = getattr(settings.limits, "prioritize_file_types", True)

                file_list = []
                for ext in [
                    ".py",
                    ".md",
                    ".txt",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".csv",
                    ".xlsx",
                    ".pdf",
                ]:
                    for file in self.project_path.rglob(f"*{ext}"):
                        if ".aacode" not in str(file):
                            rel_path = file.relative_to(self.project_path)
                            file_list.append(str(rel_path))
                            if len(file_list) >= max_files:
                                break
                    if len(file_list) >= max_files:
                        break

                # 智能优先级排序（如果启用）
                if prioritize and file_list:
                    file_list = self._prioritize_files(file_list)

                if file_list:
                    total_files = len(file_list)
                    if total_files >= max_files:
                        context_parts.append(
                            f"## 项目文件结构\n（显示前 {max_files} 个文件，共约 {max_files}+ 个）\n{chr(10).join(file_list)}"
                        )
                    else:
                        context_parts.append(
                            f"## 项目文件结构\n{chr(10).join(file_list)}"
                        )
                else:
                    context_parts.append("## 项目文件结构\n项目目录为空")
            except Exception as e:
                context_parts.append(f"## 项目文件结构\n获取失败: {str(e)[:100]}")
        except Exception as e:
            context_parts.append(f"## 项目文件结构\n获取失败: {str(e)[:100]}")

        # 确保至少返回基本信息
        if not context_parts:
            context_parts.append(f"## 工作目录\n当前工作目录: {self.project_path}")

        return "\n\n".join(context_parts)

    async def get_compact_context(self) -> str:
        """获取紧凑上下文"""
        # 直接返回简单上下文，不复杂处理
        return await self.get_context()

    async def update(self, observation: str):
        """更新上下文，记录重要信息 - 增强健壮性"""
        # 保存观察结果到临时文件，供后续查询
        if observation and len(observation) > 0:
            observation_file = self.context_dir / "latest_observation.txt"
            try:
                # 使用Python原生方式写入，增加错误处理
                observation_file.write_text(
                    observation, encoding="utf-8", errors="ignore"
                )
            except PermissionError as e:
                print(f"⚠️ 权限错误：无法写入观察文件 {observation_file}: {e}")
            except OSError as e:
                print(f"⚠️ 系统错误：无法写入观察文件 {observation_file}: {e}")
            except Exception as e:
                # 静默失败，不影响主流程
                pass

            # 保存观察历史（追加模式，保留最近5次观察）
            history_file = self.context_dir / "observation_history.txt"
            try:
                # 读取现有历史
                existing_history = ""
                if history_file.exists():
                    try:
                        existing_history = history_file.read_text(
                            encoding="utf-8", errors="ignore"
                        )
                    except Exception:
                        existing_history = ""

                # 分割历史记录
                history_entries = (
                    existing_history.strip().split("\n---\n")
                    if existing_history
                    else []
                )

                # 添加新观察（截断到1000字符以节省空间）
                new_entry = (
                    f"[{asyncio.get_event_loop().time():.0f}] {observation[:1000]}"
                )
                history_entries.append(new_entry)

                # 只保留最近5次观察
                if len(history_entries) > 5:
                    history_entries = history_entries[-5:]

                # 写入更新后的历史
                history_file.write_text(
                    "\n---\n".join(history_entries), encoding="utf-8", errors="ignore"
                )
            except Exception:
                # 静默失败，不影响主流程
                pass

            # 如果观察中包含错误或警告，记录到重要错误历史
            if any(
                keyword in observation.lower()
                for keyword in ["错误", "error", "失败", "failed", "警告", "warning"]
            ):
                errors_file = self.context_dir / "important_errors.txt"
                try:
                    # 追加模式，保留历史
                    existing_errors = ""
                    if errors_file.exists():
                        try:
                            existing_errors = errors_file.read_text(
                                encoding="utf-8", errors="ignore"
                            )
                        except Exception:
                            existing_errors = ""

                    # 保留最近的错误（最多3000字符）
                    new_error = f"\n[{asyncio.get_event_loop().time():.0f}] {observation[:300]}\n"
                    combined = (existing_errors + new_error)[-3000:]
                    errors_file.write_text(combined, encoding="utf-8", errors="ignore")
                except PermissionError:
                    print(f"⚠️ 权限错误：无法写入错误历史文件")
                except Exception:
                    pass

    async def save_large_output(self, output: str, filename: str) -> str:
        """保存大输出到文件，添加内容哈希避免重复归档"""
        import hashlib

        # 计算内容哈希
        content_hash = hashlib.md5(output.encode("utf-8", errors="ignore")).hexdigest()[
            :8
        ]

        # 检查是否已存在相同内容的文件
        for existing_file in self.context_dir.glob("*_*.txt"):
            if content_hash in existing_file.name:
                # 找到相同内容的文件，返回现有路径
                return str(existing_file.relative_to(self.project_path))

        # 在文件名中添加哈希值
        name_parts = filename.rsplit(".", 1)
        if len(name_parts) == 2:
            new_filename = f"{name_parts[0]}_{content_hash}.{name_parts[1]}"
        else:
            new_filename = f"{filename}_{content_hash}.txt"

        output_file = self.context_dir / new_filename

        try:
            # 直接使用 Python 写入，更可靠
            output_file.write_text(output, encoding="utf-8", errors="ignore")

            # 创建索引文件（可选）
            index_file = self.context_dir / "archive_index.txt"
            index_entry = f"{new_filename}|{content_hash}|{len(output)}|{asyncio.get_event_loop().time():.0f}\n"

            try:
                if index_file.exists():
                    with open(index_file, "a", encoding="utf-8") as f:
                        f.write(index_entry)
                else:
                    with open(index_file, "w", encoding="utf-8") as f:
                        f.write("# 归档索引\n")
                        f.write("# 格式: 文件名|哈希|大小|时间戳\n")
                        f.write(index_entry)
            except Exception:
                # 索引创建失败不影响主流程
                pass

            return str(output_file.relative_to(self.project_path))
        except Exception as e:
            return f"保存失败: {str(e)}"

    async def save_history(self, steps: List[Any]) -> str:
        """保存历史到文件"""
        history_file = (
            self.context_dir / f"history_{asyncio.get_event_loop().time()}.md"
        )

        # 简化的历史记录
        history_content = "# 执行历史\n\n"
        for i, step in enumerate(steps[-10:], 1):  # 只保存最近10步
            history_content += f"## 步骤 {i}\n"
            history_content += f"**思考**: {step.thought}\n"
            if step.actions:
                for j, action_item in enumerate(step.actions, 1):
                    history_content += f"**动作 {j}**: {action_item.action}\n"
                    if action_item.observation:
                        history_content += (
                            f"**观察 {j}**: {action_item.observation[:100]}...\n"
                        )
            history_content += "\n"

        # 跨平台写入文件（cat 是 Unix 命令，Windows 上不存在）
        try:
            history_file.write_text(history_content, encoding="utf-8")
            return str(history_file.relative_to(self.project_path))
        except Exception as e:
            return f"保存失败: {str(e)}"

    def _prioritize_files(self, file_list: List[str]) -> List[str]:
        """
        智能优先级排序文件列表

        优先级规则：
        1. 配置文件和文档（README, init.md, config等）
        2. 数据文件（csv, xlsx, pdf）
        3. 源代码文件（py, js, ts等）
        4. 其他文件

        Args:
            file_list: 文件路径列表

        Returns:
            排序后的文件列表
        """

        def get_priority(filepath: str) -> int:
            """获取文件优先级（数字越小优先级越高）"""
            filepath_lower = filepath.lower()
            filename = filepath.split("/")[-1].lower()

            # 优先级1：重要配置和文档（0-9）
            if filename in ["readme.md", "init.md", "readme.txt"]:
                return 0
            if filename.startswith("readme"):
                return 1
            if filename in [
                "config.yaml",
                "config.yml",
                "config.json",
                "aacode_config.yaml",
            ]:
                return 2
            if filename.endswith((".yaml", ".yml", ".json")) and "config" in filename:
                return 3
            if filename == "requirements.txt":
                return 4
            if filename == "package.json":
                return 5

            # 优先级2：数据文件（10-19）
            if filename.endswith(".csv"):
                return 10
            if filename.endswith(".xlsx"):
                return 11
            if filename.endswith(".pdf"):
                return 12

            # 优先级3：主要源代码（20-29）
            if filename in ["main.py", "app.py", "index.py", "__init__.py"]:
                return 20
            if filename in ["main.js", "app.js", "index.js"]:
                return 21
            if filename.endswith(".py"):
                return 25
            if filename.endswith((".js", ".ts", ".jsx", ".tsx")):
                return 26

            # 优先级4：其他文档（30-39）
            if filename.endswith(".md"):
                return 30
            if filename.endswith(".txt"):
                return 31

            # 优先级5：其他文件（40+）
            return 40

        # 按优先级和文件名排序
        sorted_list = sorted(file_list, key=lambda f: (get_priority(f), f))
        return sorted_list
