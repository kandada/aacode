# 原子工具 - 简化版
# tools/atomic_tools.py
"""
轻量级原子工具
遵循"bash是万能适配器"原则,简化实现
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional


class AtomicTools:
    """简化的原子工具集"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard

    async def read_file(
        self,
        path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        读取文件内容 - 支持行范围读取和智能分段提示

        Args:
            path: 文件路径(相对或绝对)
            line_start: 起始行号(从1开始,可选)
            line_end: 结束行号(包含,可选)

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            包含文件内容的字典
        """
        try:
            # 转换为 Path 对象并处理绝对/相对路径
            path_obj = Path(path)

            if path_obj.is_absolute():
                # 绝对路径:直接使用
                full_path = path_obj
                # 尝试转换为相对路径用于显示
                try:
                    display_path = str(path_obj.relative_to(self.project_path))
                except ValueError:
                    display_path = str(path_obj)
            else:
                # 相对路径:拼接到 project_path
                full_path = self.project_path / path
                display_path = path

            # 安全检查
            if not self.safety_guard.is_safe_path(full_path):
                return {"error": f"访问路径超出项目范围: {display_path}"}

            # 检查文件是否存在
            if not full_path.exists():
                return {"error": f"文件不存在: {display_path}"}

            # 检查是否为文件
            if not full_path.is_file():
                return {"error": f"路径不是文件: {display_path}"}

            # 使用bash万能适配器 - 使用绝对路径避免cwd问题
            result = await asyncio.create_subprocess_exec(
                "cat",
                str(full_path.absolute()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                error_msg = stderr.decode() if stderr else "读取文件失败"
                return {"error": f"读取文件失败: {error_msg}"}

            content = stdout.decode("utf-8", errors="ignore")
            lines = content.split("\n")
            total_lines = len(lines)

            # 如果指定了行范围,提取相应的行
            if line_start is not None or line_end is not None:
                # 处理行号(从1开始转换为从0开始的索引)
                start_idx = (line_start - 1) if line_start is not None else 0
                end_idx = (line_end - 1) if line_end is not None else total_lines

                # 边界检查
                start_idx = max(0, min(start_idx, total_lines))
                end_idx = max(0, min(end_idx, total_lines))

                # 检查是否有效的范围
                if start_idx <= end_idx:
                    # 提取行 (end_idx需要+1因为切片不包含结束索引)
                    selected_lines = lines[start_idx:end_idx + 1]
                    content = "\n".join(selected_lines)

                    return {
                        "success": True,
                        "path": display_path,
                        "content": content,
                        "size": len(content),
                        "lines": len(selected_lines),
                        "line_range": f"{start_idx + 1}-{end_idx + 1}",
                        "total_lines": total_lines,
                    }
                else:
                    # 无效的范围，返回整个文件
                    print(
                        f"⚠️  警告: 无效的行范围 {line_start}-{line_end}, 返回整个文件"
                    )

            # 读取整个文件 - 智能分段提示
            from config import settings

            max_auto_read_lines = getattr(settings.limits, "max_auto_read_lines", 200)

            if total_lines > max_auto_read_lines:
                # 文件较大,提供智能提示
                return await self._handle_large_file(
                    display_path, full_path, content, lines, total_lines
                )

            # 文件不大,直接返回
            return {
                "success": True,
                "path": display_path,
                "content": content,
                "size": len(content),
                "lines": total_lines,  # 使用 total_lines 而不是 len(lines)
            }
        except Exception as e:
            return {"error": f"读取文件异常: {str(e)},路径: {path}"}

    async def _handle_large_file(
        self,
        path: str,
        full_path: Path,
        content: str,
        lines: List[str],
        total_lines: int,
    ) -> Dict[str, Any]:
        """
        处理大文件 - 提供智能分段建议

        Args:
            path: 相对路径
            full_path: 绝对路径
            content: 文件内容
            lines: 文件行列表
            total_lines: 总行数

        Returns:
            包含建议的字典
        """
        file_ext = full_path.suffix

        # 尝试分析代码结构(仅对代码文件)
        code_extensions = [
            ".py",
            ".js",
            ".ts",
            ".java",
            ".cpp",
            ".c",
            ".go",
            ".rs",
            ".php",
            ".rb",
        ]

        if file_ext in code_extensions:
            try:
                from utils.code_analyzer import CodeAnalyzer

                analyzer = CodeAnalyzer(self.project_path)
                analysis = analyzer.analyze_code(content, file_ext)

                # 生成结构摘要
                structure_info = self._generate_structure_summary(analysis, path)

                # 生成分段建议
                suggestions = self._generate_smart_suggestions(
                    path, total_lines, analysis
                )

                return {
                    "success": True,
                    "path": path,
                    "total_lines": total_lines,
                    "size": len(content),
                    "warning": f"⚠️  文件较大({total_lines}行),建议分段读取或按结构读取",
                    "structure": structure_info,
                    "suggestions": suggestions,
                    "preview": "\n".join(lines[:50])
                    + f"\n\n... (还有 {total_lines - 50} 行)",
                    "note": "💡 提示:使用 line_start 和 line_end 参数读取特定范围,或参考上面的结构信息选择需要的部分",
                }
            except Exception as e:
                # 代码分析失败,返回简单提示
                print(f"⚠️  代码分析失败: {e}")
                pass

        # 非代码文件或分析失败,返回简单的分段建议
        return {
            "success": True,
            "path": path,
            "total_lines": total_lines,
            "size": len(content),
            "warning": f"⚠️  文件较大({total_lines}行),建议分段读取",
            "suggestions": [
                f"📖 读取前100行: read_file(path='{path}', line_end=100)",
                f"📖 读取第100-200行: read_file(path='{path}', line_start=100, line_end=200)",
                f"📖 读取中间部分: read_file(path='{path}', line_start={total_lines//2-50}, line_end={total_lines//2+50})",
                f"📖 读取末尾100行: read_file(path='{path}', line_start={max(1, total_lines-100)})",
            ],
            "preview": "\n".join(lines[:50]) + f"\n\n... (还有 {total_lines - 50} 行)",
            "note": "💡 提示:使用 line_start 和 line_end 参数读取特定范围",
        }

    def _generate_structure_summary(self, analysis, path: str) -> Dict[str, Any]:
        """生成代码结构摘要"""
        summary = {
            "total_lines": analysis.lines_of_code,
            "complexity": round(analysis.complexity_score, 2),
        }

        # 函数列表
        if analysis.functions:
            summary["functions"] = [
                {
                    "name": f["name"],
                    "line": f["line"],
                    "args": f.get("args", []),
                    "suggestion": f"read_file(path='{path}', line_start={f['line']}, line_end={f['line']+20})",
                }
                for f in analysis.functions[:10]  # 最多显示10个
            ]
            if len(analysis.functions) > 10:
                summary["functions_note"] = (
                    f"... 还有 {len(analysis.functions) - 10} 个函数"
                )

        # 类列表
        if analysis.classes:
            summary["classes"] = [
                {
                    "name": c["name"],
                    "line": c["line"],
                    "methods": c.get("methods", []),
                    "suggestion": f"read_file(path='{path}', line_start={c['line']}, line_end={c['line']+50})",
                }
                for c in analysis.classes[:5]  # 最多显示5个
            ]
            if len(analysis.classes) > 5:
                summary["classes_note"] = f"... 还有 {len(analysis.classes) - 5} 个类"

        # 导入列表
        if analysis.imports:
            summary["imports"] = analysis.imports[:10]
            if len(analysis.imports) > 10:
                summary["imports_note"] = (
                    f"... 还有 {len(analysis.imports) - 10} 个导入"
                )

        return summary

    def _generate_smart_suggestions(
        self, path: str, total_lines: int, analysis
    ) -> List[str]:
        """生成智能分段建议"""
        suggestions = []

        # 基于函数的建议
        if analysis.functions:
            func = analysis.functions[0]
            suggestions.append(
                f"📖 读取第一个函数 '{func['name']}': read_file(path='{path}', line_start={func['line']}, line_end={func['line']+30})"
            )

        # 基于类的建议
        if analysis.classes:
            cls = analysis.classes[0]
            suggestions.append(
                f"📖 读取第一个类 '{cls['name']}': read_file(path='{path}', line_start={cls['line']}, line_end={cls['line']+50})"
            )

        # 通用建议
        suggestions.extend(
            [
                f"📖 读取前100行: read_file(path='{path}', line_end=100)",
                f"📖 读取中间部分: read_file(path='{path}', line_start={total_lines//2-50}, line_end={total_lines//2+50})",
                f"📖 读取末尾: read_file(path='{path}', line_start={max(1, total_lines-100)})",
            ]
        )

        return suggestions

    async def write_file(self, path: str, content: Optional[str] = None, source: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        写入文件 - 不仅支持模型写入内容，也支持从上下文引用内容
        
        支持两种方式写入文件：
        1. 直接提供内容：content="文件内容"
        2. 从上下文引用：source="引用标识符"（如"last_web_fetch"、"tool_result:fetch_url"等）
        
         当使用source参数时，支持以下过滤参数（可选）：
         - source_start_line: 源文件起始行号（1-based，包含）- **必须使用**
         - source_end_line: 源文件结束行号（1-based，包含）- **必须使用**
         - source_pattern: 源文件正则表达式模式，只保留匹配的行 - **必须使用**
         - source_exclude_pattern: 源文件正则表达式模式，排除匹配的行 - **必须使用**
        
        **重要规则**：当使用source参数时，所有源文件过滤参数必须使用source_前缀。
                    使用不带前缀的参数将触发警告。
        
        示例：
        - 写入文件前10行：{"path": "output.txt", "source": "file:input.txt", "source_start_line": 1, "source_end_line": 10}
        - 只写入包含"def "的行：{"path": "functions.txt", "source": "file:code.py", "source_pattern": "^def "}
        - 排除注释行：{"path": "clean.txt", "source": "file:code.py", "source_exclude_pattern": "^#"}
        
        注意:**kwargs 用于接收过滤参数和其他额外参数
        """
        try:
            # 转换为 Path 对象
            path_obj = Path(path)

            # 处理路径
            if path_obj.is_absolute():
                # 绝对路径:直接使用
                full_path = path_obj
                # 尝试转换为相对路径用于显示
                try:
                    display_path = str(path_obj.relative_to(self.project_path))
                except ValueError:
                    display_path = str(path_obj)
            else:
                # 相对路径:规范化并拼接到 project_path
                # 注意：使用 removeprefix 而不是 lstrip，因为 lstrip 会错误地移除路径中的点号
                path_str = str(path_obj)
                # 安全地移除开头的 "./" 前缀，但保留 ".aacode" 这样的目录名
                # 使用正则表达式或简单逻辑：只移除开头的 "./" 如果后面跟着的不是 "."
                if path_str.startswith("./"):
                    # 检查第二个字符之后是否是 "."（如 "./.aacode"）
                    if len(path_str) > 2 and path_str[2] == ".":
                        # 这是 "./.aacode" 的情况，只移除 "./"
                        path_normalized = path_str[2:]  # 变成 ".aacode"
                    else:
                        # 这是 "./test.py" 的情况，移除 "./"
                        path_normalized = path_str[2:]
                elif path_str == ".":
                    path_normalized = ""  # 当前目录
                else:
                    path_normalized = path_str
                full_path = self.project_path / path_normalized
                display_path = path_normalized

            # 安全检查
            if not self.safety_guard.is_safe_path(full_path):
                return {"error": f"写入路径超出项目范围: {display_path}"}

            # 使用bash万能适配器
            # 先创建目录,再写入文件
            mkdir_cmd = f"mkdir -p {full_path.parent}"
            mkdir_process = await asyncio.create_subprocess_shell(
                mkdir_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )

            mkdir_stdout, mkdir_stderr = await mkdir_process.communicate()
            if mkdir_process.returncode != 0:
                return {
                    "error": f"创建目录失败: {mkdir_stderr.decode() if mkdir_stderr else '未知错误'}"
                }

            # 处理内容来源
            final_content = None
            
            if source:
                # 源文件参数检查：当使用source参数时，必须使用source_前缀
                # 检查行范围参数 - 不告警，只记录信息
                if 'start_line' in kwargs or 'end_line' in kwargs:
                    print(f"📝 信息：当使用source参数时，start_line/end_line参数被忽略")
                    print(f"   如需指定源文件行范围，请使用source_start_line/source_end_line")
                
                # 检查正则表达式参数 - 不告警，只记录信息
                if 'pattern' in kwargs or 'exclude_pattern' in kwargs:
                    print(f"📝 信息：当使用source参数时，pattern/exclude_pattern参数被忽略")
                    print(f"   如需正则表达式过滤，请使用source_pattern/source_exclude_pattern")
                
                # 从上下文获取内容
                final_content = await self._get_content_from_source(source, kwargs)
                if final_content is None:
                    return {"error": f"无法从来源获取内容: {source}"}
            elif content:
                # 使用直接提供的内容
                final_content = content
            else:
                return {"error": "必须提供 content 或 source 参数"}
            
            # 使用Python原生方式写入文件,避免shell权限问题
            try:
                full_path.write_text(final_content, encoding="utf-8")
                print(f"✅ 文件已写入: {display_path} ({len(final_content)} 字符)")
            except PermissionError as e:
                return {"error": f"写入文件权限错误: {str(e)},路径: {display_path}"}
            except Exception as e:
                return {"error": f"写入文件失败: {str(e)},路径: {display_path}"}

            return {
                "success": True,
                "path": display_path,
                "size": len(final_content),
                "lines": len(final_content.split("\n")),
                "absolute_path": str(full_path),
                "source_used": "source" if source else "content",
            }
        except Exception as e:
            return {"error": f"写入文件异常: {str(e)},路径: {path}"}

    def _filter_content(self, content: str, kwargs: Dict[str, Any]) -> str:
        """
         根据过滤参数处理内容（仅用于源文件过滤）
        
        Args:
            content: 原始内容
            kwargs: 过滤参数，支持：
                   - source_start_line: 源文件起始行号（1-based，包含）- **必须使用**
                   - source_end_line: 源文件结束行号（1-based，包含）- **必须使用**
                   - source_pattern: 源文件正则表达式模式，只保留匹配的行 - **必须使用**
                   - source_exclude_pattern: 源文件正则表达式模式，排除匹配的行 - **必须使用**
        
        注意：此方法仅用于过滤源文件内容。当使用source参数时，所有源文件过滤参数必须使用source_前缀。
              使用不带前缀的参数将触发警告。
        
        Returns:
            过滤后的内容
        """
        lines = content.split('\n')
        filtered_lines = []
        
        # 应用行范围过滤 - 强制使用source_前缀参数
        start_line = kwargs.get('source_start_line')
        end_line = kwargs.get('source_end_line')
        
        # 检查是否使用了start_line/end_line作为源文件参数
        if 'start_line' in kwargs or 'end_line' in kwargs:
            print(f"📝 信息：start_line/end_line参数被忽略（源文件过滤）")
            print(f"   如需指定源文件行范围，请使用source_start_line/source_end_line")
        
        if start_line is not None or end_line is not None:
            # 自动调整行号0为1，保持与_parse_line_range一致
            if start_line is not None:
                start_line = max(1, int(start_line))
            if end_line is not None:
                end_line = max(1, int(end_line))
            
            # 确保 start_line <= end_line，与_parse_line_range保持一致
            if start_line is not None and end_line is not None and start_line > end_line:
                start_line, end_line = end_line, start_line
            
            start = int(start_line) - 1 if start_line is not None else 0
            end = int(end_line) if end_line is not None else len(lines)
            
            # 边界检查
            start = max(0, min(start, len(lines)))
            end = max(start, min(end, len(lines)))
            
            lines = lines[start:end]
            if start_line or end_line:
                print(f"📏 应用行范围过滤(source_): 第{start+1}-{end}行")
        
        # 应用正则表达式过滤 - 强制使用source_前缀参数
        pattern = kwargs.get('source_pattern')
        exclude_pattern = kwargs.get('source_exclude_pattern')
        
        # 检查是否使用了不带前缀的正则表达式参数
        if 'pattern' in kwargs or 'exclude_pattern' in kwargs:
            print(f"📝 信息：pattern/exclude_pattern参数被忽略（源文件过滤）")
            print(f"   如需正则表达式过滤，请使用source_pattern/source_exclude_pattern")
        
        if pattern or exclude_pattern:
            import re
            
            # 计算起始行号用于日志（使用调整后的start_line）
            actual_start = start_line if start_line is not None else 1
            
            for i, line in enumerate(lines):
                line_num = actual_start + i
                
                # 排除模式优先
                if exclude_pattern:
                    if re.search(exclude_pattern, line):
                        continue
                
                # 包含模式
                if pattern:
                    if re.search(pattern, line):
                        filtered_lines.append(line)
                else:
                    filtered_lines.append(line)
            
            if pattern:
                print(f"🔍 应用包含模式过滤(source_): '{pattern}'，保留 {len(filtered_lines)} 行")
            if exclude_pattern:
                print(f"🚫 应用排除模式过滤(source_): '{exclude_pattern}'，排除 {len(lines) - len(filtered_lines)} 行")
            
            lines = filtered_lines
        
        return '\n'.join(lines)

    async def _get_content_from_source(self, source: str, kwargs: Dict[str, Any]) -> Optional[str]:
        """
        从指定来源获取内容，支持部分内容提取
        
        Args:
            source: 来源标识符，支持以下格式：
                   - "last_tool_result": 获取最近一次工具执行结果
                   - "tool_result:<tool_name>": 获取指定工具的结果
                   - "conversation": 获取对话历史中的内容
                   - "clipboard": 获取剪贴板内容（如果可用）
                   - 直接内容：如果source以"content:"开头，则提取后面的内容
                   - 文件内容：如果source以"file:"开头，则从文件读取
                   - 其他自定义标识符
            kwargs: 工具调用时的额外参数，支持以下过滤参数：
                   - start_line: 起始行号（1-based，包含）
                   - end_line: 结束行号（1-based，包含）
                   - pattern: 正则表达式模式，只保留匹配的行
                   - exclude_pattern: 正则表达式模式，排除匹配的行
        
        Returns:
            内容字符串或None（如果无法获取）
        """
        try:
            print(f"🔍 尝试从来源获取内容: {source}")
            
            # 方案1：直接内容（通过kwargs传递）
            if "direct_content" in kwargs:
                print(f"📝 使用直接传递的内容 ({len(kwargs['direct_content'])} 字符)")
                content = kwargs["direct_content"]
                return self._filter_content(content, kwargs)
            
            # 方案2：source包含直接内容（格式：content:实际内容）
            if source.startswith("content:"):
                content = source[8:]  # 移除"content:"前缀
                print(f"📝 从source参数提取内容 ({len(content)} 字符)")
                return self._filter_content(content, kwargs)
            
            # 方案3：从文件读取（格式：file:文件路径）
            if source.startswith("file:"):
                file_path = source[5:]  # 移除"file:"前缀
                try:
                    full_path = self.project_path / file_path
                    if full_path.exists():
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        print(f"📄 从文件读取内容: {file_path} ({len(content)} 字符)")
                        filtered_content = self._filter_content(content, kwargs)
                        if filtered_content != content:
                            print(f"✅ 内容过滤完成: {len(content)} → {len(filtered_content)} 字符")
                        return filtered_content
                    else:
                        print(f"⚠️  文件不存在: {file_path}")
                        return None
                except Exception as e:
                    print(f"⚠️  读取文件失败: {str(e)}")
                    return None
            
            # 方案4：从上下文文件读取（.aacode/context目录）
            # 首先尝试直接文件名
            context_file = self.project_path / ".aacode" / "context" / f"{source}.txt"
            if context_file.exists():
                try:
                    content = context_file.read_text(encoding="utf-8", errors="ignore")
                    print(f"📁 从上下文文件读取: {source} ({len(content)} 字符)")
                    filtered_content = self._filter_content(content, kwargs)
                    if filtered_content != content:
                        print(f"✅ 内容过滤完成: {len(content)} → {len(filtered_content)} 字符")
                    return filtered_content
                except Exception as e:
                    print(f"⚠️  读取上下文文件失败: {str(e)}")
                    return None
            
            # 尝试不带.txt后缀
            context_file_no_ext = self.project_path / ".aacode" / "context" / source
            if context_file_no_ext.exists():
                try:
                    content = context_file_no_ext.read_text(encoding="utf-8", errors="ignore")
                    print(f"📁 从上下文文件读取(无后缀): {source} ({len(content)} 字符)")
                    filtered_content = self._filter_content(content, kwargs)
                    if filtered_content != content:
                        print(f"✅ 内容过滤完成: {len(content)} → {len(filtered_content)} 字符")
                    return filtered_content
                except Exception as e:
                    print(f"⚠️  读取上下文文件失败: {str(e)}")
                    return None
            
            # 方案5：特殊标识符处理
            if source == "last_web_fetch" or source == "tool_result:fetch_url":
                # 尝试查找最近的web_fetch结果
                web_fetch_file = self.project_path / ".aacode" / "context" / "web_fetch_result.txt"
                if web_fetch_file.exists():
                    try:
                        content = web_fetch_file.read_text(encoding="utf-8", errors="ignore")
                        print(f"🌐 使用最近web_fetch结果 ({len(content)} 字符)")
                        filtered_content = self._filter_content(content, kwargs)
                        if filtered_content != content:
                            print(f"✅ 内容过滤完成: {len(content)} → {len(filtered_content)} 字符")
                        return filtered_content
                    except Exception as e:
                        print(f"⚠️  读取web_fetch结果失败: {str(e)}")
                        return None
            
            print(f"⚠️  无法识别的来源标识符: {source}")
            print(f"💡 提示：支持的格式：")
            print(f"   - content:<直接内容>")
            print(f"   - file:<文件路径>")
            print(f"   - 上下文文件名（存储在.aacode/context/）")
            print(f"   - last_web_fetch（最近web_fetch结果）")
            print(f"   - tool_result:fetch_url（fetch_url工具结果）")
            print(f"💡 过滤参数（可选）：")
            print(f"   - start_line: 起始行号（如: 10）")
            print(f"   - end_line: 结束行号（如: 20）")
            print(f"   - pattern: 正则表达式模式（如: '^def '）")
            print(f"   - exclude_pattern: 排除模式（如: '^#'）")
            
            return None
            
        except Exception as e:
            print(f"⚠️  从来源获取内容失败: {str(e)}")
            return None



    async def run_shell(
        self, command: str, timeout: int = 120, **kwargs
    ) -> Dict[str, Any]:
        """
        执行shell命令(带安全护栏)

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数
        """
        try:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            if timeout is None:
                from config import settings

                timeout = settings.timeouts.shell_command

            # 安全检查
            safety_check = self.safety_guard.check_command(command)
            if not safety_check["allowed"]:
                return {
                    "error": f"命令被安全护栏拒绝: {safety_check['reason']}",
                    "allowed": False,
                    "command": command,
                }

            # 在项目目录下执行
            print(f"🔧 执行命令: {command}")

            # 异步执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.project_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                stdout_text = stdout.decode("utf-8", errors="ignore")
                stderr_text = stderr.decode("utf-8", errors="ignore")

                # 打印输出预览(使用配置的预览长度)
                from config import settings

                preview_length = settings.limits.shell_output_preview

                # 关键改进：run_shell 工具总是成功的（只要命令能执行）
                # 命令的退出码只是返回信息的一部分，不代表工具失败

                # 打印输出预览
                if stdout_text:
                    preview = (
                        stdout_text[:preview_length] + "..."
                        if len(stdout_text) > preview_length
                        else stdout_text
                    )
                    print(f"📤 输出: {preview}")

                if stderr_text and process.returncode != 0:
                    # 只有在命令失败时才打印 stderr
                    stderr_preview = (
                        stderr_text[:preview_length] + "..."
                        if len(stderr_text) > preview_length
                        else stderr_text
                    )
                    print(f"⚠️  错误输出: {stderr_preview}")

                # 统一返回格式：工具总是成功，返回完整的命令执行信息
                return {
                    "success": True,  # 工具执行成功
                    "returncode": process.returncode,  # 命令退出码
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "command": command,
                    "working_directory": str(self.project_path),
                }
            except asyncio.TimeoutError:
                process.terminate()
                return {
                    "success": True,  # 工具执行成功
                    "error": f"命令执行超时 ({timeout}秒)",
                    "timeout": True,
                    "command": command,
                    "working_directory": str(self.project_path),
                }

        except Exception as e:
            # 只有工具本身出现异常时才返回 success=False
            error_type = type(e).__name__
            error_msg = f"工具执行异常: {error_type}: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,  # 工具执行失败
                "error": error_msg,
                "command": command,
                "working_directory": str(self.project_path),
            }

    async def list_files(
        self, pattern: str = "*", max_results: int = 100, grep: str = "", **kwargs
    ) -> Dict[str, Any]:
        """
        列出文件 - 增强实现，支持文件列表和内容搜索

        Args:
            pattern: 文件名匹配模式(支持通配符),如 "*.py","test_*"
                    注意:如果传入路径(如 ".","./"),会自动转换为 "*"
            max_results: 返回的最大文件数量
            grep: 可选，搜索文件内容的关键词。如果提供，将搜索包含该关键词的文件

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数(如recursive等)，也用于接收别名参数
        """
        try:
            # 处理别名参数
            # 检查是否有通过别名传递的grep参数（如search, query等）
            grep_aliases = ["search", "query", "text", "keyword"]
            for alias in grep_aliases:
                if alias in kwargs and kwargs[alias]:
                    grep = kwargs[alias]
                    break

            # 检查是否有通过别名传递的pattern参数（如glob, path等）
            pattern_aliases = ["glob", "path", "file_pattern", "directory", "dir"]
            for alias in pattern_aliases:
                if alias in kwargs and kwargs[alias]:
                    pattern = kwargs[alias]
                    break

            # 使用配置的最大结果数(来自 aacode_config.yaml)
            from config import settings

            if max_results == 100:  # 使用默认值，检查配置
                max_results = settings.limits.max_file_list_results

            # 智能处理:如果pattern看起来像路径,转换为通配符
            if pattern in [".", "./", "/", "", ".."] or pattern.endswith("/"):
                original_pattern = pattern
                pattern = "*"
                print(
                    f"💡 提示:已将路径参数 '{original_pattern}' 转换为文件模式 '*'(列出所有文件)"
                )

            # 检查是否进行内容搜索
            if grep:
                print(f"🔍 搜索模式: 在文件 '{pattern}' 中搜索 '{grep}'")
                return await self._search_with_grep(pattern, grep, max_results)
            else:
                # 普通文件列表模式
                print(f"📁 列表模式: 列出文件 '{pattern}'")
                return await self._list_files_only(pattern, max_results)

        except Exception as e:
            return {"error": str(e)}

    async def _list_files_only(self, pattern: str, max_results: int) -> Dict[str, Any]:
        """仅列出文件（不搜索内容）"""
        # 使用bash万能适配器
        cmd = f"find . -name '{pattern}' -type f | head -{max_results}"

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.project_path,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {"error": stderr.decode() if stderr else "列出文件失败"}

        files = []
        for line in stdout.decode().strip().split("\n"):
            if line.strip() and ".aacode" not in line:
                rel_path = line.strip()[2:]  # 移除 './'
                files.append(
                    {"path": rel_path, "size": 0, "is_dir": False}  # 简化,不获取大小
                )

        return {"success": True, "files": files, "count": len(files), "mode": "list"}

    async def _search_with_grep(
        self, pattern: str, grep: str, max_results: int
    ) -> Dict[str, Any]:
        """使用grep搜索文件内容"""
        try:
            import subprocess

            # 检查是否安装了rg (ripgrep)
            use_rg = False
            try:
                import shutil

                if shutil.which("rg"):
                    use_rg = True
            except:
                pass

            if use_rg:
                # 使用ripgrep进行高效搜索
                cmd = [
                    "rg",
                    "-i",  # 忽略大小写
                    "-n",  # 显示行号
                    "-H",  # 显示文件名
                    "--color",
                    "never",
                    grep,
                    str(self.project_path),
                    "-g",
                    pattern,
                    "-m",
                    str(max_results),  # 最大结果数
                ]
            else:
                # 使用标准grep作为后备
                cmd = [
                    "grep",
                    "-r",  # 递归搜索
                    "-i",  # 忽略大小写
                    "-n",  # 显示行号
                    "-H",  # 显示文件名
                    grep,
                    "--include",
                    pattern,
                    ".",
                    "|",
                    "head",
                    "-n",
                    str(max_results * 10),  # 粗略限制结果数
                ]

            if use_rg:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_path),
                )
            else:
                # 对于grep命令，使用shell模式
                cmd_str = " ".join(cmd)
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_path),
                )

            stdout, stderr = await process.communicate()

            if process.returncode not in [0, 1]:  # 0: 找到结果, 1: 没找到
                return {"error": f"搜索失败: {stderr.decode()}", "success": False}

            # 收集结果，按文件分组
            file_results = {}
            for line in stdout.decode().split("\n"):
                if line.strip():
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path, line_num, content = (
                            parts[0],
                            parts[1],
                            ":".join(parts[2:]),
                        )

                        # 处理文件路径：可能是相对路径或绝对路径
                        try:
                            # 如果是绝对路径，转换为相对路径
                            if file_path.startswith("/"):
                                rel_path = Path(file_path).relative_to(
                                    self.project_path
                                )
                                file_str = str(rel_path)
                            else:
                                # 已经是相对路径
                                file_str = file_path
                                # 移除开头的'./'如果存在
                                if file_str.startswith("./"):
                                    file_str = file_str[2:]
                        except ValueError:
                            # 路径转换失败，使用原始路径
                            file_str = file_path

                        if file_str not in file_results:
                            file_results[file_str] = {
                                "path": file_str,
                                "size": 0,
                                "is_dir": False,
                                "matches": [],
                            }

                        file_results[file_str]["matches"].append(
                            {"line": int(line_num), "content": content.strip()}
                        )

            # 转换为files格式
            files = list(file_results.values())

            # 计算总匹配数
            total_matches = sum(len(file_info["matches"]) for file_info in files)

            return {
                "success": True,
                "files": files,
                "count": len(files),
                "total_matches": total_matches,
                "mode": "search",
                "query": grep,
            }

        except Exception as e:
            return {"error": str(e), "success": False}

    async def search_files(
        self, query: str, file_pattern: str = "*.py", max_results: int = 20, **kwargs
    ) -> Dict[str, Any]:
        """
        搜索文件内容 - 在文件中搜索文本,使用grep-like功能

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数
        """
        try:
            import subprocess

            # 使用配置的最大结果数(来自 aacode_config.yaml)
            from config import settings

            if max_results == 20:  # 使用默认值，检查配置
                max_results = settings.limits.max_search_results

            # 检查是否安装了rg (ripgrep)
            use_rg = False
            try:
                import shutil

                if shutil.which("rg"):
                    use_rg = True
            except:
                pass

            if use_rg:
                # 使用ripgrep进行高效搜索
                cmd = [
                    "rg",
                    "-i",  # 忽略大小写
                    "-n",  # 显示行号
                    "-H",  # 显示文件名
                    "--color",
                    "never",
                    query,
                    str(self.project_path),
                    "-g",
                    file_pattern,
                    "-m",
                    str(max_results),  # 最大结果数
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_path),
                )
            else:
                # 使用标准grep作为后备
                cmd_str = f"grep -r -i -n -H '{query}' --include '{file_pattern}' . | head -n {max_results * 10}"
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_path),
                )

            stdout, stderr = await process.communicate()

            if process.returncode not in [0, 1]:  # 0: 找到结果, 1: 没找到
                return {"error": f"搜索失败: {stderr.decode()}", "success": False}

            results = []
            for line in stdout.decode().split("\n"):
                if line.strip():
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path, line_num, content = (
                            parts[0],
                            parts[1],
                            ":".join(parts[2:]),
                        )

                        # 处理文件路径：可能是相对路径或绝对路径
                        try:
                            # 如果是绝对路径，转换为相对路径
                            if file_path.startswith("/"):
                                rel_path = Path(file_path).relative_to(
                                    self.project_path
                                )
                            else:
                                # 已经是相对路径
                                rel_path = Path(file_path)
                                # 移除开头的'./'如果存在
                                if str(rel_path).startswith("./"):
                                    rel_path = Path(str(rel_path)[2:])
                        except ValueError:
                            # 路径转换失败，使用原始路径
                            rel_path = Path(file_path)
                        results.append(
                            {
                                "file": str(rel_path),
                                "line": int(line_num),
                                "content": content.strip(),
                            }
                        )

            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
            }

        except FileNotFoundError:
            # ripgrep不可用,使用Python实现
            return await self._python_search(query, file_pattern, max_results)
        except Exception as e:
            return {"error": str(e)}

    async def _python_search(
        self, query: str, file_pattern: str, max_results: int
    ) -> Dict[str, Any]:
        """Python实现的文件搜索 - 简化版"""
        try:
            # 使用bash万能适配器作为备选
            # 添加 -n 参数确保输出行号
            cmd = (
                f"grep -rn --include='{file_pattern}' '{query}' . | head -{max_results}"
            )

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )

            stdout, stderr = await process.communicate()

            # grep 返回1表示没找到匹配，这是正常的
            if process.returncode not in [0, 1]:
                return {
                    "success": True,
                    "error": f"搜索命令失败: {stderr.decode() if stderr else '未知错误'}",
                    "query": query,
                    "results": [],
                    "count": 0,
                }

            results = []
            output = stdout.decode().strip()

            if not output:
                # 没有匹配结果
                return {"success": True, "query": query, "results": [], "count": 0}

            for line in output.split("\n"):
                if line.strip() and ".aacode" not in line:
                    # 尝试解析 文件:行号:内容 格式
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        try:
                            file_path = parts[0]
                            # 移除 './' 前缀
                            if file_path.startswith("./"):
                                file_path = file_path[2:]

                            # 尝试解析行号
                            line_num = None
                            content = ""

                            if len(parts) >= 3:
                                try:
                                    line_num = int(parts[1])
                                    content = parts[2]
                                except ValueError:
                                    # 行号解析失败，可能格式不对
                                    content = ":".join(parts[1:])
                            else:
                                content = parts[1]

                            result = {"file": file_path, "content": content}

                            if line_num is not None:
                                result["line"] = str(line_num)

                            results.append(result)
                        except Exception as e:
                            # 解析失败，跳过这一行
                            print(f"⚠️  解析搜索结果失败: {line[:50]}... 错误: {e}")
                            continue

            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {
                "success": True,
                "error": f"搜索异常: {str(e)}",
                "query": query,
                "results": [],
                "count": 0,
            }
