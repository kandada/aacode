# 增量更新工具
# tools/incremental_tools.py
#!/usr/bin/env python3
"""
增量更新工具
支持智能的代码增量更新,避免重写整个文件
"""

import difflib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import asyncio


class IncrementalTools:
    """增量更新工具类"""

    def __init__(self, project_path: Path, safety_guard: Any = None):
        self.project_path = project_path
        self.safety_guard = safety_guard

    async def incremental_update(
        self, path: str, new_content: Optional[str] = None, update_type: str = "smart", 
        source: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        增量更新文件 - 不仅支持模型写入内容，也支持从上下文引用内容

        Args:
            path: 文件路径
            new_content: 新内容（与source二选一）
            update_type: 更新类型 ("smart", "replace", "append", "prepend", "line_update", "insert_before", "insert_after")
            source: 内容来源标识符（与new_content二选一），支持格式：
                   - content:<直接内容>
                   - file:<文件路径>
                   - 上下文文件名
                   - last_web_fetch等

         参数说明：
        - **源文件参数**（当使用source参数时）：
          - source_start_line: 源文件起始行号（1-based，包含）
          - source_end_line: 源文件结束行号（1-based，包含）
          - source_pattern: 源文件正则表达式模式，只保留匹配的行
          - source_exclude_pattern: 源文件正则表达式模式，排除匹配的行
        
        - **目标文件参数**（更新位置）：
          - line_number: 目标文件行号（用于line_update, insert_before, insert_after, replace操作）
          - line_range: 目标文件行范围，如 "10-20"（用于line_update, replace操作）
          - start_line: 目标文件起始行（用于replace操作）
          - end_line: 目标文件结束行（用于replace操作）
          - reference_content: 参考内容（用于insert_before, insert_after）

        重要规则：
        1. 当使用source参数时，所有源文件过滤参数必须使用source_前缀
        2. 当使用new_content参数时，使用start_line/end_line或line_number指定目标文件行范围
        3. 为了安全，replace操作默认替换整个文件，只有明确指定行范围时才进行部分替换
        
        - **目标文件参数**（更新位置）：
          - line_number: 目标文件行号（用于line_update, insert_before, insert_after, replace操作）
          - line_range: 目标文件行范围，如 "10-20"（用于line_update, replace操作）
          - start_line: 目标文件起始行（用于replace操作）
          - end_line: 目标文件结束行（用于replace操作）
          - reference_content: 参考内容（用于insert_before, insert_after）

        重要规则：
        1. 当使用source参数时，必须使用source_start_line/source_end_line指定源文件行范围
        2. 当使用new_content参数时，使用start_line/end_line或line_number指定目标文件行范围
        3. 为了安全，replace操作默认替换整个文件，只有明确指定行范围时才进行部分替换

         示例：
        - 从源文件提取50-60行更新到目标文件第10行（正确用法）：
          {"path": "output.txt", "source": "file:input.txt", "source_start_line": 50, 
           "source_end_line": 60, "update_type": "line_update", "line_number": 10}
        
        - 替换目标文件5-10行（正确用法）：
          {"path": "output.txt", "new_content": "new content", "update_type": "replace", 
           "start_line": 5, "end_line": 10}
        
        - 替换目标文件第132-145行（使用line_number和end_line）：
          {"path": "output.txt", "new_content": "new content", "update_type": "replace", 
           "line_number": 132, "end_line": 145}
        
        - 错误用法（将导致警告）：
          {"path": "output.txt", "source": "file:input.txt", "start_line": 50, 
           "end_line": 60, "update_type": "line_update", "line_number": 10}

        注意:**kwargs 用于接收过滤参数和其他额外参数

        Returns:
            操作结果
        """
        # 调试：打印调用参数
        print(f"🔧 incremental_update 被调用: path={path}, update_type={update_type}, kwargs={kwargs}")
        
        full_path = self.project_path / path

        # 安全检查
        if self.safety_guard and not self.safety_guard.is_safe_path(full_path):
            error_msg = {"error": "访问路径超出项目范围"}
            print(f"❌ 安全检查失败: {error_msg}")
            return error_msg

        # 处理内容来源
        final_content = None
        
        if source:
            # 从上下文获取内容
            final_content = await self._get_content_from_source(source, kwargs)
            if final_content is None and new_content is not None:
                # source获取失败，有new_content作为fallback
                print(f"📝 从source获取内容失败，fallback到new_content")
                final_content = new_content
            elif final_content is None:
                return {"error": f"无法从来源获取内容: {source}"}
        elif new_content is not None:
            # 使用直接提供的内容（包括空字符串）
            final_content = new_content
        else:
            return {"error": "必须提供 new_content 或 source 参数"}

        # 参数验证
        validation_error = self._validate_update_params(update_type, kwargs)
        if validation_error:
            print(f"❌ 参数验证失败: {validation_error}")
            return {"error": validation_error}
        
        # 源文件参数检查：当使用source参数时，必须使用source_前缀
        if source:
            # 检查行范围参数 - 不告警，只记录信息
            if 'start_line' in kwargs or 'end_line' in kwargs:
                print(f"📝 信息：当使用source参数时，start_line/end_line参数被忽略")
                print(f"   如需指定源文件行范围，请使用source_start_line/source_end_line")
            
            # 检查正则表达式参数 - 不告警，只记录信息
            if 'pattern' in kwargs or 'exclude_pattern' in kwargs:
                print(f"📝 信息：当使用source参数时，pattern/exclude_pattern参数被忽略")
                print(f"   如需正则表达式过滤，请使用source_pattern/source_exclude_pattern")
        
        # 检查文件是否存在
        file_exists = full_path.exists()

        if not file_exists:
            # 文件不存在,直接创建
            result = await self._create_new_file(full_path, final_content, path)
            if result.get("success"):
                print(f"✅ {result.get('message', '文件已创建')}")
            return result

        # 检查文件大小限制
        try:
            file_size = full_path.stat().st_size
            MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB限制
            if file_size > MAX_FILE_SIZE:
                return {"error": f"文件过大 ({file_size/1024/1024:.1f}MB)，超过限制 ({MAX_FILE_SIZE/1024/1024}MB)"}
        except Exception as e:
            print(f"⚠️  检查文件大小失败: {str(e)}")
            # 继续执行，不阻止操作

        # 创建备份
        backup_path = self._create_backup(full_path)
        
        # 读取现有内容（尝试多种编码）
        old_content = None
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'gbk', 'gb2312']
        
        for encoding in encodings_to_try:
            try:
                old_content = full_path.read_text(encoding=encoding)
                print(f"📖 使用编码 {encoding} 成功读取文件")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"⚠️  使用编码 {encoding} 读取失败: {str(e)}")
                continue
        
        if old_content is None:
            # 如果读取失败，尝试恢复备份
            if backup_path:
                self._restore_backup(full_path, backup_path)
            return {"error": f"读取文件失败: 尝试了多种编码({', '.join(encodings_to_try)})均失败"}

        # 执行更新操作
        result = None
        try:
            if update_type == "replace":
                # 检查是否有行范围参数
                start_line = kwargs.get("start_line")
                end_line = kwargs.get("end_line")
                line_number = kwargs.get("line_number")
                line_range_param = kwargs.get("line_range")
                
                if start_line is not None or end_line is not None or line_number is not None or line_range_param is not None:
                    # 安全警告：replace操作检测到行范围参数，将进行部分替换
                    print(f"⚠️  安全提示：replace操作检测到行范围参数，将替换指定行范围而非整个文件")
                    print(f"   参数: start_line={start_line}, end_line={end_line}, line_number={line_number}, line_range={line_range_param}")
                    print(f"   注意：如果没有行范围参数，replace将替换整个文件")
                    
                    # 确定最终的行范围
                    final_line_range = None
                    
                    if line_range_param is not None:
                        # 优先使用line_range参数
                        final_line_range = line_range_param
                    elif line_number is not None:
                        # 使用line_number参数（可能单独使用，也可能与end_line一起使用）
                        if end_line is not None:
                            # line_number作为起始行，end_line作为结束行
                            final_line_range = f"{line_number}-{end_line}"
                        else:
                            # 单行更新
                            final_line_range = str(line_number)
                    elif start_line is not None or end_line is not None:
                        # 将start_line和end_line转换为line_range格式
                        if start_line is None:
                            start_line = 1
                        if end_line is None:
                            # 如果没有end_line，使用start_line作为单行更新
                            final_line_range = str(start_line)
                        else:
                            final_line_range = f"{start_line}-{end_line}"
                    
                    print(f"   转换后: line_range={final_line_range}")
                    
                    result = await self._line_update(
                        full_path, final_content, path, old_content, 
                        line_range=final_line_range
                    )
                else:
                    # 安全提示：没有行范围参数，替换整个文件
                    print(f"📝 replace操作：未指定行范围参数，将替换整个文件")
                    print(f"   如需部分替换，请使用start_line/end_line或line_range参数")
                    
                    result = await self._replace_file(
                        full_path, final_content, path, old_content
                    )
            elif update_type == "append":
                # 追加内容
                result = await self._append_to_file(
                    full_path, final_content, path, old_content
                )
            elif update_type == "prepend":
                # 前置内容
                result = await self._prepend_to_file(
                    full_path, final_content, path, old_content
                )
            elif update_type == "line_update":
                # 行级别更新
                line_number = kwargs.get("line_number")
                line_range = kwargs.get("line_range")
                result = await self._line_update(
                    full_path, final_content, path, old_content, line_number, line_range
                )
            elif update_type == "insert_before":
                # 在指定行之前插入
                line_number = kwargs.get("line_number")
                reference_content = kwargs.get("reference_content")
                result = await self._insert_before(
                    full_path, final_content, path, old_content, line_number, reference_content
                )
            elif update_type == "insert_after":
                # 在指定行之后插入
                line_number = kwargs.get("line_number")
                reference_content = kwargs.get("reference_content")
                result = await self._insert_after(
                    full_path, final_content, path, old_content, line_number, reference_content
                )
            else:  # smart
                # 智能更新:分析差异,只更新必要的部分
                result = await self._smart_update(
                    full_path, final_content, path, old_content
                )
            
            # 检查结果
            if result and result.get("success"):
                print(f"✅ {result.get('message', '操作成功')}")
                # 清理备份
                self._cleanup_backup(backup_path)
                return result
            else:
                # 操作失败，恢复备份
                if backup_path:
                    if self._restore_backup(full_path, backup_path):
                        error_msg = result.get("error", "操作失败") if result else "操作失败"
                        return {"error": f"{error_msg}，已恢复备份"}
                
                return result or {"error": "操作失败"}
                
        except Exception as e:
            # 异常情况，恢复备份
            if backup_path:
                self._restore_backup(full_path, backup_path)
            error_msg = {"error": f"增量更新失败: {str(e)}"}
            print(f"❌ 增量更新异常: {error_msg}")
            return error_msg

    def _validate_update_params(self, update_type: str, kwargs: Dict[str, Any]) -> Optional[str]:
        """
        验证更新参数
        
        Args:
            update_type: 更新类型
            kwargs: 参数字典
            
        Returns:
            错误消息或None（如果验证通过）
        """
        valid_update_types = [
            "smart", "replace", "append", "prepend", 
            "line_update", "insert_before", "insert_after"
        ]
        
        if update_type not in valid_update_types:
            return f"无效的update_type: {update_type}。有效的类型: {', '.join(valid_update_types)}"
        
        # 检查特定模式所需的参数
        if update_type == "line_update":
            if "line_number" not in kwargs and "line_range" not in kwargs:
                return "line_update模式需要line_number或line_range参数"
        
        elif update_type in ["insert_before", "insert_after"]:
            if "line_number" not in kwargs and "reference_content" not in kwargs:
                return f"{update_type}模式需要line_number或reference_content参数"
        
        # 安全提示：检查replace操作是否包含行范围参数
        if update_type == "replace":
            has_line_params = any(key in kwargs for key in ["start_line", "end_line", "line_range", "line_number"])
            if has_line_params:
                print(f"📝 安全提示：replace操作包含行范围参数，将替换指定行范围而非整个文件")
                print(f"   检测到的参数: {[k for k in ['start_line', 'end_line', 'line_range', 'line_number'] if k in kwargs]}")
                print(f"   注意：如果没有行范围参数，replace将替换整个文件")
        
        # 检查参数类型
        if "line_number" in kwargs:
            try:
                line_num = int(kwargs["line_number"])
                # 允许自动调整，不在验证阶段拒绝
                # 实际调整在具体方法中处理
            except (ValueError, TypeError):
                return f"line_number必须是整数，当前值: {kwargs['line_number']}"
        
        if "line_range" in kwargs:
            line_range = kwargs["line_range"]
            if not isinstance(line_range, str):
                return f"line_range必须是字符串，当前类型: {type(line_range)}"
            
            # 更宽松的格式检查，让_parse_line_range处理具体解析
            line_range = line_range.strip()
            if not line_range:
                return "line_range不能为空"
            
            # 基本格式检查
            import re
            if not re.match(r'^(-?\d*)-(-?\d*)$', line_range) and not re.match(r'^\d+$', line_range):
                return f"line_range格式错误，应为'start-end'、'start-'、'-end'或单行号，当前值: {line_range}"
            
            # 对于包含连字符的格式，检查是否至少有一个数字
            if '-' in line_range:
                parts = line_range.split('-')
                if len(parts) != 2:
                    return f"line_range格式错误，应为'start-end'、'start-'或'-end'，当前值: {line_range}"
                
                start_str, end_str = parts[0].strip(), parts[1].strip()
                
                # 检查是否都是空字符串（只有"-"的情况）
                if not start_str and not end_str:
                    return "line_range不能只有连字符'-'"
                
                # 检查起始部分
                if start_str:
                    try:
                        start = int(start_str)
                        if start < 1:
                            print(f"📝 信息：起始行号 {start} 小于1，将自动调整到第1行")
                    except ValueError:
                        return f"起始行包含非数字字符: {start_str}"
                
                # 检查结束部分
                if end_str:
                    try:
                        end = int(end_str)
                        if end < 1:
                            print(f"📝 信息：结束行号 {end} 小于1，将自动调整到第1行")
                    except ValueError:
                        return f"结束行包含非数字字符: {end_str}"
            else:
                # 单行格式
                try:
                    line_num = int(line_range)
                    if line_num < 1:
                        print(f"📝 信息：行号 {line_num} 小于1，将自动调整到第1行")
                except ValueError:
                    return f"line_range包含非数字字符: {line_range}"
        
        return None
    
    def _create_backup(self, full_path: Path) -> Optional[Path]:
        """
        创建文件备份
        
        Args:
            full_path: 原始文件路径
            
        Returns:
            备份文件路径或None（如果备份失败）
        """
        try:
            if not full_path.exists():
                print(f"📝 无需备份: 文件不存在 {full_path.name}")
                return None
            
            # 检查文件大小
            try:
                file_size = full_path.stat().st_size
                if file_size > 100 * 1024 * 1024:  # 100MB限制
                    print(f"⚠️  文件过大 ({file_size/1024/1024:.1f}MB)，跳过备份")
                    return None
            except Exception as e:
                print(f"⚠️  检查文件大小失败: {str(e)}")
                # 继续尝试备份
            
            # 创建备份文件名（添加时间戳避免冲突）
            import time
            timestamp = int(time.time())
            backup_path = full_path.with_suffix(f"{full_path.suffix}.{timestamp}.backup")
            
            # 如果备份文件已存在，尝试其他名称
            counter = 1
            while backup_path.exists() and counter < 10:
                backup_path = full_path.with_suffix(f"{full_path.suffix}.{timestamp}.{counter}.backup")
                counter += 1
            
            if backup_path.exists():
                print(f"⚠️  无法创建唯一备份文件，跳过备份")
                return None
            
            # 复制文件
            import shutil
            shutil.copy2(full_path, backup_path)
            
            print(f"📋 创建备份: {full_path.name} -> {backup_path.name}")
            return backup_path
            
        except PermissionError as e:
            print(f"❌ 创建备份失败 - 权限错误: {str(e)}")
            return None
        except OSError as e:
            print(f"❌ 创建备份失败 - 系统错误: {str(e)}")
            return None
        except Exception as e:
            print(f"⚠️  创建备份失败: {str(e)}")
            return None
    
    def _restore_backup(self, full_path: Path, backup_path: Optional[Path]) -> bool:
        """
        从备份恢复文件
        
        Args:
            full_path: 原始文件路径
            backup_path: 备份文件路径
            
        Returns:
            是否成功恢复
        """
        if backup_path is None:
            print(f"📝 无需恢复: 备份文件路径为None")
            return False
        
        if not backup_path.exists():
            print(f"⚠️  无法恢复: 备份文件不存在 {backup_path.name}")
            return False
        
        try:
            # 检查备份文件是否可读
            try:
                backup_size = backup_path.stat().st_size
                if backup_size == 0:
                    print(f"⚠️  备份文件为空: {backup_path.name}")
                    return False
            except Exception as e:
                print(f"⚠️  检查备份文件失败: {str(e)}")
                # 继续尝试恢复
            
            # 创建恢复前的临时备份（防止恢复失败）
            recovery_backup = None
            if full_path.exists():
                try:
                    import time
                    timestamp = int(time.time())
                    recovery_backup = full_path.with_suffix(f"{full_path.suffix}.recovery.{timestamp}.tmp")
                    import shutil
                    shutil.copy2(full_path, recovery_backup)
                    print(f"📋 创建恢复前备份: {recovery_backup.name}")
                except Exception as e:
                    print(f"⚠️  创建恢复前备份失败: {str(e)}")
                    # 继续恢复
            
            # 执行恢复
            import shutil
            shutil.copy2(backup_path, full_path)
            print(f"🔄 从备份恢复文件: {backup_path.name} -> {full_path.name}")
            
            # 清理恢复前备份
            if recovery_backup and recovery_backup.exists():
                try:
                    recovery_backup.unlink()
                    print(f"🧹 清理恢复前备份: {recovery_backup.name}")
                except Exception as e:
                    print(f"⚠️  清理恢复前备份失败: {str(e)}")
            
            return True
            
        except PermissionError as e:
            print(f"❌ 恢复备份失败 - 权限错误: {str(e)}")
            return False
        except OSError as e:
            print(f"❌ 恢复备份失败 - 系统错误: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ 恢复备份失败: {str(e)}")
            import traceback
            print(f"   堆栈跟踪: {traceback.format_exc()}")
            return False
    
    def _cleanup_backup(self, backup_path: Optional[Path]):
        """
        清理备份文件
        
        Args:
            backup_path: 备份文件路径
        """
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
                print(f"🧹 清理备份文件: {backup_path.name}")
            except Exception as e:
                print(f"⚠️  清理备份失败: {str(e)}")
    
    def _split_lines_preserving_newlines(self, content: str) -> List[str]:
        """
        分割内容为行，每行以换行符结尾
        
        Args:
            content: 文本内容
            
        Returns:
            行列表，每行以换行符结尾
        """
        if not content:
            return []
        
        lines = []
        i = 0
        n = len(content)
        
        while i < n:
            j = i
            # 查找行结束位置（\n 或 \r 或 \r\n）
            while j < n and content[j] != '\n' and content[j] != '\r':
                j += 1
            
            line = content[i:j]
            
            # 处理换行符
            if j < n:
                if content[j] == '\r':
                    if j + 1 < n and content[j + 1] == '\n':
                        # \r\n 换行
                        line += '\n'
                        j += 2
                    else:
                        # 单独的 \r 换行
                        line += '\n'
                        j += 1
                else:
                    # \n 换行
                    line += '\n'
                    j += 1
            else:
                # 最后一行没有换行符，添加一个
                line += '\n'
            
            lines.append(line)
            i = j
        
        return lines
    
    def _join_lines_preserving_newlines(self, lines: List[str]) -> str:
        """
        合并行为内容，确保行与行正确分隔
        
        Args:
            lines: 行列表（每行以换行符结尾）
            
        Returns:
            合并后的内容
        """
        if not lines:
            return ''
        
        # 确保每行都有换行符，然后连接
        result_lines = []
        for line in lines:
            if line.endswith('\n'):
                result_lines.append(line)
            else:
                result_lines.append(line + '\n')
        
        # 连接所有行
        result = ''.join(result_lines)
        
        # 确保最后一行有换行符（保持一致性）
        if result and not result.endswith('\n'):
            result += '\n'
            
        return result
    
    def _parse_line_range(self, line_range: str, total_lines: int) -> Tuple[int, int]:
        """
        解析行范围字符串
        
        Args:
            line_range: 行范围字符串，如 "10-20"、"10"、"8-"、"-3"、"5-"
            total_lines: 总行数
            
        Returns:
            (start_index, end_index) 0-based索引，end_index不包含
        """
        line_range = line_range.strip()
        
        if not line_range:
            raise ValueError("行范围不能为空")
        
        import re
        
        # 支持多种格式：
        # 1. "10" - 单行
        # 2. "10-20" - 标准范围
        # 3. "10-" - 从第10行到文件末尾
        # 4. "-20" - 从文件开始到第20行
        # 5. "-" - 整个文件
        
        # 检查是否是单行号
        if re.match(r'^\d+$', line_range):
            try:
                line_num = int(line_range)
                if line_num < 1:
                    line_num = 1  # 自动调整到第一行
                if line_num > total_lines and total_lines > 0:
                    line_num = total_lines  # 自动调整到最后一行
                
                # 单行更新：替换该行
                start_index = line_num - 1
                end_index = line_num  # 单行：结束行号=开始行号（不包含）
                return start_index, end_index
            except ValueError:
                raise ValueError(f"无效的行号: {line_range}")
        
        # 检查范围格式
        range_pattern = r'^(-?\d*)-(-?\d*)$'
        match = re.match(range_pattern, line_range)
        if not match:
            raise ValueError(f"无效的行范围格式: {line_range}，应为 'start-end'、'start-'、'-end' 或单行号")
        
        start_str, end_str = match.group(1), match.group(2)
        
        # 解析起始行
        if start_str:
            try:
                start_line = int(start_str)
                if start_line < 1:
                    start_line = 1
            except ValueError:
                raise ValueError(f"起始行包含非数字字符: {start_str}")
        else:
            start_line = 1  # 默认从第一行开始
        
        # 解析结束行
        if end_str:
            try:
                end_line = int(end_str)
                if end_line < 1:
                    end_line = 1
            except ValueError:
                raise ValueError(f"结束行包含非数字字符: {end_str}")
        else:
            end_line = total_lines  # 默认到文件末尾
        
        # 自动调整边界
        if start_line > end_line:
            # 自动交换，使起始行 <= 结束行
            start_line, end_line = end_line, start_line
        
        # 转换为0-based索引
        start_index = start_line - 1
        end_index = end_line  # end_line是1-based包含，作为0-based不包含正好
        
        # 边界检查（针对调整后的值）
        if start_index < 0:
            start_index = 0
        if start_index >= total_lines:
            if total_lines > 0:
                start_index = total_lines - 1  # 调整到最后一行
            else:
                start_index = 0  # 空文件
        
        if end_index > total_lines:
            end_index = total_lines
        if end_index < 0:
            end_index = 0
        
        # 确保 start_index <= end_index
        if start_index > end_index:
            start_index, end_index = end_index, start_index
        
        # 最终验证：确保至少更新一行（如果文件非空）
        if start_index >= end_index:
            if total_lines == 0:
                # 空文件，无法更新任何行
                raise ValueError(f"文件为空，无法更新行")
            else:
                # 调整end_index，确保至少更新一行
                end_index = start_index + 1
                if end_index > total_lines:
                    end_index = total_lines
        
        return start_index, end_index
    
    def _find_line_by_content(self, lines: List[str], reference_content: str, start_from: int = 0) -> Optional[int]:
        """
        通过内容查找行
        
        Args:
            lines: 行列表
            reference_content: 参考内容
            start_from: 开始搜索的行号（0-based）
            
        Returns:
            行号（0-based）或None
        """
        if not reference_content:
            return None
        
        reference_content = reference_content.strip()
        if not reference_content:
            return None
        
        import re
        
        # 策略列表，按优先级排序
        strategies = [
            self._exact_match,
            self._strip_match,
            self._contains_match,
            self._fuzzy_match,
            self._regex_match,
        ]
        
        for strategy in strategies:
            result = strategy(lines, reference_content, start_from)
            if result is not None:
                print(f"🔍 使用策略 {strategy.__name__} 找到匹配行: {result + 1}")
                return result
        
        print(f"🔍 未找到包含参考内容的行: {reference_content[:50]}...")
        return None
    
    def _exact_match(self, lines: List[str], reference: str, start_from: int) -> Optional[int]:
        """精确匹配"""
        for i in range(start_from, len(lines)):
            if lines[i] == reference:
                return i
        return None
    
    def _strip_match(self, lines: List[str], reference: str, start_from: int) -> Optional[int]:
        """去除空白后匹配"""
        for i in range(start_from, len(lines)):
            if lines[i].strip() == reference:
                return i
        return None
    
    def _contains_match(self, lines: List[str], reference: str, start_from: int) -> Optional[int]:
        """包含匹配"""
        for i in range(start_from, len(lines)):
            if reference in lines[i]:
                return i
        return None
    
    def _fuzzy_match(self, lines: List[str], reference: str, start_from: int) -> Optional[int]:
        """模糊匹配（忽略多余空白）"""
        # 将参考内容拆分为关键词
        keywords = [kw.strip() for kw in reference.split() if kw.strip()]
        if not keywords:
            return None
        
        for i in range(start_from, len(lines)):
            line = lines[i]
            # 检查是否包含所有关键词
            if all(keyword in line for keyword in keywords):
                return i
        return None
    
    def _regex_match(self, lines: List[str], reference: str, start_from: int) -> Optional[int]:
        """正则表达式匹配"""
        try:
            # 尝试将参考内容作为正则表达式
            pattern = re.compile(reference)
            for i in range(start_from, len(lines)):
                if pattern.search(lines[i]):
                    return i
        except re.error:
            # 如果不是有效的正则表达式，尝试转义后匹配
            try:
                pattern = re.compile(re.escape(reference))
                for i in range(start_from, len(lines)):
                    if pattern.search(lines[i]):
                        return i
            except:
                pass
        return None
    
    def _atomic_write(self, full_path: Path, content: str, encoding: str = "utf-8") -> bool:
        """
        原子性写入文件
        
        Args:
            full_path: 文件路径
            content: 要写入的内容
            encoding: 编码
            
        Returns:
            是否成功
        """
        import tempfile
        import os
        import stat
        
        success = False
        temp_path = None
        original_mode = None
        
        try:
            # 保存原始文件的权限（如果存在）
            if full_path.exists():
                try:
                    original_mode = os.stat(full_path).st_mode
                except Exception as e:
                    print(f"⚠️  无法获取原始文件权限: {str(e)}")
            
            # 确保目录存在
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding=encoding,
                suffix='.tmp',
                prefix=full_path.name + '.',
                dir=full_path.parent,
                delete=False
            ) as f:
                temp_path = f.name
                f.write(content)
            
            # 设置临时文件权限（如果原始文件有特殊权限）
            if original_mode:
                try:
                    os.chmod(temp_path, original_mode)
                except Exception as e:
                    print(f"⚠️  无法设置临时文件权限: {str(e)}")
            
            # 原子性替换
            os.replace(temp_path, str(full_path))
            success = True
            print(f"⚛️  原子性写入完成: {full_path.name}")
            
        except PermissionError as e:
            print(f"❌ 原子性写入失败 - 权限错误: {str(e)}")
            print(f"   文件: {full_path}")
            print(f"   临时文件: {temp_path}")
            
        except OSError as e:
            print(f"❌ 原子性写入失败 - 系统错误: {str(e)}")
            print(f"   错误代码: {e.errno if hasattr(e, 'errno') else 'N/A'}")
            
        except Exception as e:
            print(f"❌ 原子性写入失败: {str(e)}")
            import traceback
            print(f"   堆栈跟踪: {traceback.format_exc()}")
            
        finally:
            # 清理临时文件（如果替换失败）
            if not success and temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    print(f"🧹 清理临时文件: {temp_path}")
                except Exception as e:
                    print(f"⚠️  清理临时文件失败: {str(e)}")
        
        return success

    async def _create_new_file(
        self, full_path: Path, content: str, rel_path: str
    ) -> Dict[str, Any]:
        """创建新文件"""
        try:
            # 创建目录
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # 原子性写入文件
            if not self._atomic_write(full_path, content):
                return {"error": "创建文件失败"}

            return {
                "success": True,
                "path": rel_path,
                "action": "created",
                "size": len(content),
                "message": f"创建新文件: {rel_path}",
            }
        except Exception as e:
            return {"error": f"创建文件失败: {str(e)}"}

    async def _replace_file(
        self, full_path: Path, new_content: str, rel_path: str, old_content: str
    ) -> Dict[str, Any]:
        """替换整个文件"""
        try:
            # 检查内容是否相同
            if old_content == new_content:
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(new_content),
                    "message": f"文件内容未变化: {rel_path}",
                }

            # 原子性写入新内容
            if not self._atomic_write(full_path, new_content):
                return {"error": "原子性写入失败"}

            # 计算差异
            diff_count = self._count_differences(old_content, new_content)

            return {
                "success": True,
                "path": rel_path,
                "action": "replaced",
                "size": len(new_content),
                "diff_count": diff_count,
                "message": f"替换文件: {rel_path} ({diff_count} 处差异)",
            }
        except Exception as e:
            return {"error": f"替换文件失败: {str(e)}"}

    async def _append_to_file(
        self, full_path: Path, new_content: str, rel_path: str, old_content: str
    ) -> Dict[str, Any]:
        """追加内容到文件"""
        try:
            # 检查是否已经包含该内容（更精确的检查）
            old_lines = self._split_lines_preserving_newlines(old_content)
            new_lines = self._split_lines_preserving_newlines(new_content)
            
            # 检查新内容是否已经是旧内容的最后几行
            if new_lines and len(old_lines) >= len(new_lines):
                if old_lines[-len(new_lines):] == new_lines:
                    return {
                        "success": True,
                        "path": rel_path,
                        "action": "unchanged",
                        "size": len(old_content),
                        "message": f"内容已存在,无需追加: {rel_path}",
                    }

            # 追加内容，正确处理换行符
            if old_content and not old_content.endswith('\n'):
                updated_content = old_content + '\n' + new_content
            else:
                updated_content = old_content + new_content
            
            # 原子性写入
            if not self._atomic_write(full_path, updated_content):
                return {"error": "原子性写入失败"}

            return {
                "success": True,
                "path": rel_path,
                "action": "appended",
                "size": len(updated_content),
                "added_size": len(new_content),
                "message": f"追加内容到文件: {rel_path}",
            }
        except Exception as e:
            return {"error": f"追加内容失败: {str(e)}"}

    async def _prepend_to_file(
        self, full_path: Path, new_content: str, rel_path: str, old_content: str
    ) -> Dict[str, Any]:
        """前置内容到文件"""
        try:
            # 检查是否已经包含该内容
            old_lines = self._split_lines_preserving_newlines(old_content)
            new_lines = self._split_lines_preserving_newlines(new_content)
            
            # 检查新内容是否已经是旧内容的前几行
            if new_lines and len(old_lines) >= len(new_lines):
                if old_lines[:len(new_lines)] == new_lines:
                    return {
                        "success": True,
                        "path": rel_path,
                        "action": "unchanged",
                        "size": len(old_content),
                        "message": f"内容已存在,无需前置: {rel_path}",
                    }

            # 前置内容，正确处理换行符
            if new_content and not new_content.endswith('\n'):
                updated_content = new_content + '\n' + old_content
            else:
                updated_content = new_content + old_content
            
            # 原子性写入
            if not self._atomic_write(full_path, updated_content):
                return {"error": "原子性写入失败"}

            return {
                "success": True,
                "path": rel_path,
                "action": "prepended",
                "size": len(updated_content),
                "added_size": len(new_content),
                "message": f"前置内容到文件: {rel_path}",
            }
        except Exception as e:
            return {"error": f"前置内容失败: {str(e)}"}

    async def _line_update(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        line_number: Optional[int] = None,
        line_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """行级别更新：更新指定行或行范围"""
        try:
            # 使用保留换行符的方式分割行
            old_lines = self._split_lines_preserving_newlines(old_content)
            total_lines = len(old_lines)
            
            # 处理空文件特殊情况
            if total_lines == 0:
                # 空文件，直接替换整个文件
                if not self._atomic_write(full_path, new_content):
                    return {"error": "原子性写入失败"}
                
                new_lines_count = len(self._split_lines_preserving_newlines(new_content))
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "line_updated",
                    "size": len(new_content),
                    "lines_updated": 0,
                    "new_lines_count": new_lines_count,
                    "line_range": "1-1",
                    "message": f"行级别更新 {rel_path}: 空文件替换为新内容 ({new_lines_count} 行)",
                }
            
            # 解析行范围
            start_index = None
            end_index = None
            
            if line_number is not None:
                # 确保line_number是整数
                try:
                    line_number = int(line_number)
                except (ValueError, TypeError):
                    return {"error": f"line_number必须是整数，当前值: {line_number}"}
                
                # 单行更新
                if line_number < 1:
                    line_number = 1
                
                # 处理越界行号：如果行号超过总行数，则追加到文件末尾
                if line_number > total_lines:
                    # 追加新内容到文件末尾，正确处理换行符
                    # 确保追加的内容以换行符开头（如果旧内容不以换行结尾）
                    # 并确保追加的内容以换行符结尾（保持文件格式一致）
                    content_to_append = new_content
                    if not content_to_append.endswith('\n'):
                        content_to_append += '\n'
                    
                    if old_content and not old_content.endswith('\n'):
                        updated_content = old_content + '\n' + content_to_append
                    else:
                        updated_content = old_content + content_to_append
                    
                    if not self._atomic_write(full_path, updated_content):
                        return {"error": "原子性写入失败"}
                    
                    new_lines_count = len(self._split_lines_preserving_newlines(new_content))
                    return {
                        "success": True,
                        "path": rel_path,
                        "action": "appended",
                        "size": len(updated_content),
                        "added_size": len(new_content),
                        "message": f"行级别更新 {rel_path}: 行号{line_number}超过总行数{total_lines}，已追加到文件末尾 ({new_lines_count} 行)",
                    }
                
                start_index = line_number - 1  # 转换为0-based索引
                end_index = line_number  # 单行：结束行号=开始行号（不包含）
            elif line_range is not None:
                # 行范围更新
                try:
                    start_index, end_index = self._parse_line_range(line_range, total_lines)
                except ValueError as e:
                    return {"error": f"无效的行范围: {str(e)}"}
            else:
                return {"error": "必须提供 line_number 或 line_range 参数"}
            
            # 最终边界检查（确保索引有效）
            if start_index < 0:
                start_index = 0
            if start_index >= total_lines:
                if total_lines > 0:
                    start_index = total_lines - 1
                else:
                    start_index = 0
            
            if end_index > total_lines:
                end_index = total_lines
            if end_index < 0:
                end_index = 0
            
            # 确保 start_index <= end_index
            if start_index > end_index:
                start_index, end_index = end_index, start_index
            
            # 确保至少更新一行（如果文件非空）
            if start_index >= end_index:
                if total_lines > 0:
                    end_index = start_index + 1
                    if end_index > total_lines:
                        end_index = total_lines
                else:
                    # 空文件，已经处理过了
                    pass
            
            # 分割新内容为行（保留换行符）
            new_lines = self._split_lines_preserving_newlines(new_content)
            
            # 替换指定行范围
            updated_lines = old_lines.copy()
            updated_lines[start_index:end_index] = new_lines
            
            # 构建更新后的内容
            updated_content = self._join_lines_preserving_newlines(updated_lines)
            
            # 原子性写入
            if not self._atomic_write(full_path, updated_content):
                return {"error": "原子性写入失败"}
            
            # 计算更新的行数
            lines_updated = end_index - start_index
            new_lines_count = len(new_lines)
            
            # 显示给用户的行号（1-based）
            display_start = start_index + 1
            display_end = end_index  # end_index是0-based不包含，作为显示给用户的结束行号（不包含）
            
            return {
                "success": True,
                "path": rel_path,
                "action": "line_updated",
                "size": len(updated_content),
                "lines_updated": lines_updated,
                "new_lines_count": new_lines_count,
                "line_range": f"{display_start}-{display_end}",
                "message": f"行级别更新 {rel_path}: 更新了第 {display_start}-{display_end} 行 ({lines_updated} 行 → {new_lines_count} 行)",
            }
            
        except Exception as e:
            return {"error": f"行级别更新失败: {str(e)}"}

    async def _insert_before(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        line_number: Optional[int] = None,
        reference_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在指定行之前插入内容"""
        try:
            # 使用保留换行符的方式分割行
            old_lines = self._split_lines_preserving_newlines(old_content)
            total_lines = len(old_lines)
            
            # 确定插入位置
            insert_index = None
            
            if line_number is not None:
                # 使用行号定位
                if line_number < 1:
                    line_number = 1
                if line_number > total_lines:
                    line_number = total_lines
                insert_index = line_number - 1  # 转换为0-based索引
            elif reference_content is not None:
                # 使用参考内容定位
                insert_index = self._find_line_by_content(old_lines, reference_content)
                
                if insert_index is None:
                    return {"error": f"未找到包含参考内容的行: {reference_content}"}
            else:
                return {"error": "必须提供 line_number 或 reference_content 参数"}
            
            # 分割新内容为行（保留换行符）
            new_lines = self._split_lines_preserving_newlines(new_content)
            
            # 在指定位置插入新内容
            updated_lines = old_lines.copy()
            updated_lines[insert_index:insert_index] = new_lines
            
            # 构建更新后的内容
            updated_content = self._join_lines_preserving_newlines(updated_lines)
            
            # 原子性写入
            if not self._atomic_write(full_path, updated_content):
                return {"error": "原子性写入失败"}
            
            # 计算插入的行数
            lines_inserted = len(new_lines)
            # 显示给用户的行号（插入位置的行号）
            # 如果使用line_number参数，line_number就是插入位置的行号
            # 如果使用reference_content，需要计算
            if line_number is not None:
                display_line = line_number
            else:
                # 使用reference_content找到的行号
                display_line = insert_index + 1 if insert_index is not None else 1
            
            return {
                "success": True,
                "path": rel_path,
                "action": "inserted_before",
                "size": len(updated_content),
                "lines_inserted": lines_inserted,
                "insert_position": f"第{display_line}行之前",
                "message": f"在 {rel_path} 的第{display_line}行之前插入了 {lines_inserted} 行",
            }
            
        except Exception as e:
            return {"error": f"插入内容失败: {str(e)}"}

    async def _insert_after(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        line_number: Optional[int] = None,
        reference_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在指定行之后插入内容"""
        try:
            # 使用保留换行符的方式分割行
            old_lines = self._split_lines_preserving_newlines(old_content)
            total_lines = len(old_lines)
            
            # 确定插入位置
            insert_index = None
            target_index = None  # 用于reference_content情况
            
            if line_number is not None:
                # 使用行号定位
                if line_number < 1:
                    line_number = 1
                if line_number > total_lines:
                    line_number = total_lines
                insert_index = line_number  # 在指定行之后插入，line_number是1-based，insert_index是0-based
            elif reference_content is not None:
                # 使用参考内容定位
                target_index = self._find_line_by_content(old_lines, reference_content)
                
                if target_index is None:
                    return {"error": f"未找到包含参考内容的行: {reference_content}"}
                
                insert_index = target_index + 1  # 在匹配行之后插入
            else:
                return {"error": "必须提供 line_number 或 reference_content 参数"}
            
            # 边界检查
            if insert_index > total_lines:
                insert_index = total_lines
            
            # 分割新内容为行（保留换行符）
            new_lines = self._split_lines_preserving_newlines(new_content)
            
            # 在指定位置插入新内容
            updated_lines = old_lines.copy()
            updated_lines[insert_index:insert_index] = new_lines
            
            # 构建更新后的内容
            updated_content = self._join_lines_preserving_newlines(updated_lines)
            
            # 原子性写入
            if not self._atomic_write(full_path, updated_content):
                return {"error": "原子性写入失败"}
            
            # 计算插入的行数
            lines_inserted = len(new_lines)
            # 显示给用户的行号（插入位置之前的行号）
            display_line = line_number if line_number is not None else (target_index + 1 if target_index is not None else 1)
            
            return {
                "success": True,
                "path": rel_path,
                "action": "inserted_after",
                "size": len(updated_content),
                "lines_inserted": lines_inserted,
                "insert_position": f"第{display_line}行之后",
                "message": f"在 {rel_path} 的第{display_line}行之后插入了 {lines_inserted} 行",
            }
            
        except Exception as e:
            return {"error": f"插入内容失败: {str(e)}"}

    async def _smart_update(
        self, full_path: Path, new_content: str, rel_path: str, old_content: str
    ) -> Dict[str, Any]:
        """智能更新:分析差异并最小化更改"""
        try:
            # 如果内容相同,无需更新
            if old_content == new_content:
                result = {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(new_content),
                    "message": f"文件内容未变化: {rel_path}",
                }
                return result

            # 分析文件类型
            file_ext = full_path.suffix.lower()
            is_code_file = file_ext in [
                ".py",
                ".js",
                ".ts",
                ".java",
                ".go",
                ".rs",
                ".cpp",
                ".c",
                ".h",
            ]

            if is_code_file:
                # 对于代码文件,尝试智能合并
                return await self._smart_code_update(
                    full_path, new_content, rel_path, old_content, file_ext
                )
            else:
                # 对于非代码文件,使用差异分析
                return await self._diff_based_update(
                    full_path, new_content, rel_path, old_content
                )

        except Exception as e:
            return {"error": f"智能更新失败: {str(e)}"}

    async def _smart_code_update(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        file_ext: str,
    ) -> Dict[str, Any]:
        """智能代码更新"""
        # 分析新旧内容的函数/类结构
        old_entities = self._extract_code_entities(old_content, file_ext)
        new_entities = self._extract_code_entities(new_content, file_ext)
        
        print(f"🔍 智能更新分析: 旧实体 {len(old_entities)} 个, 新实体 {len(new_entities)} 个")

        # 情况1: 实体数量相同且名称相同 - 逐实体更新
        if len(old_entities) == len(new_entities) and len(old_entities) > 0:
            # 检查实体名称是否匹配
            names_match = all(
                old_entities[i].get("name") == new_entities[i].get("name")
                for i in range(len(old_entities))
            )

            if names_match:
                print(f"🔍 实体名称匹配，进行逐实体更新")
                # 逐实体更新
                return await self._update_entities(
                    full_path,
                    new_content,
                    rel_path,
                    old_content,
                    old_entities,
                    new_entities,
                )
        
        # 情况2: 新内容是旧内容的子集 - 部分更新
        if new_entities and old_entities:
            # 检查新实体是否都是旧实体的子集
            new_names = {e.get("name") for e in new_entities}
            old_names = {e.get("name") for e in old_entities}
            
            if new_names.issubset(old_names):
                print(f"🔍 新实体是旧实体的子集，进行部分更新")
                return await self._partial_entity_update(
                    full_path,
                    new_content,
                    rel_path,
                    old_content,
                    old_entities,
                    new_entities,
                )
        
        # 情况3: 尝试基于名称的匹配更新
        if new_entities and old_entities:
            print(f"🔍 尝试基于名称的匹配更新")
            return await self._name_based_entity_update(
                full_path,
                new_content,
                rel_path,
                old_content,
                old_entities,
                new_entities,
            )

        # 否则使用差异分析
        print(f"🔍 无法进行智能更新，使用差异分析")
        return await self._diff_based_update(
            full_path, new_content, rel_path, old_content
        )

    def _extract_code_entities(
        self, content: str, file_ext: str
    ) -> List[Dict[str, Any]]:
        """提取代码实体(函数,类等)"""
        entities = []
        
        if file_ext == ".py":
            # 尝试使用ast模块进行准确解析
            entities = self._extract_python_entities_ast(content)
            if entities:
                print(f"🔍 使用AST解析提取了 {len(entities)} 个实体")
                return entities
            
            # 如果AST解析失败，回退到基于行的解析
            print("📝 AST解析失败，使用基于行的解析")
            entities = self._extract_python_entities_line_based(content)
        
        return entities
    
    def _extract_python_entities_ast(self, content: str) -> List[Dict[str, Any]]:
        """使用AST模块提取Python实体"""
        try:
            import ast
            lines = content.split("\n")
            entities = []
            
            class EntityVisitor(ast.NodeVisitor):
                def __init__(self, lines):
                    self.lines = lines
                    self.entities = []
                
                def visit_FunctionDef(self, node):
                    start_line = node.lineno - 1  # ast使用1-based行号
                    end_line = node.end_lineno - 1 if hasattr(node, 'end_lineno') and node.end_lineno is not None else self._find_end_line(start_line)
                    
                    self.entities.append({
                        "type": "function",
                        "name": node.name,
                        "line": start_line,
                        "start": start_line,
                        "end": end_line,
                        "signature": self._get_function_signature(node)
                    })
                    self.generic_visit(node)
                
                def visit_AsyncFunctionDef(self, node):
                    start_line = node.lineno - 1
                    end_line = node.end_lineno - 1 if hasattr(node, 'end_lineno') and node.end_lineno is not None else self._find_end_line(start_line)
                    
                    self.entities.append({
                        "type": "async_function",
                        "name": node.name,
                        "line": start_line,
                        "start": start_line,
                        "end": end_line,
                        "signature": self._get_function_signature(node)
                    })
                    self.generic_visit(node)
                
                def visit_ClassDef(self, node):
                    start_line = node.lineno - 1
                    end_line = node.end_lineno - 1 if hasattr(node, 'end_lineno') and node.end_lineno is not None else self._find_end_line(start_line)
                    
                    self.entities.append({
                        "type": "class",
                        "name": node.name,
                        "line": start_line,
                        "start": start_line,
                        "end": end_line,
                        "bases": [ast.unparse(base) for base in node.bases] if hasattr(ast, 'unparse') else []
                    })
                    self.generic_visit(node)
                
                def _find_end_line(self, start_line: int) -> int:
                    """查找实体结束行（基于缩进）"""
                    if start_line >= len(self.lines):
                        return start_line
                    
                    indent_level = len(self.lines[start_line]) - len(self.lines[start_line].lstrip())
                    
                    for i in range(start_line + 1, len(self.lines)):
                        line = self.lines[i]
                        if line.strip():  # 非空行
                            current_indent = len(line) - len(line.lstrip())
                            if current_indent <= indent_level:
                                return i - 1
                    
                    return len(self.lines) - 1
                
                def _get_function_signature(self, node):
                    """获取函数签名"""
                    try:
                        if hasattr(ast, 'unparse'):
                            # Python 3.9+ 支持 ast.unparse
                            return ast.unparse(node.args)
                    except:
                        pass
                    return ""
            
            try:
                tree = ast.parse(content)
                visitor = EntityVisitor(lines)
                visitor.visit(tree)
                return visitor.entities
            except SyntaxError as e:
                print(f"⚠️  AST解析语法错误: {e}")
                return []
            except Exception as e:
                print(f"⚠️  AST解析失败: {e}")
                return []
                
        except ImportError:
            print("⚠️  ast模块不可用")
            return []
        except Exception as e:
            print(f"⚠️  AST解析异常: {e}")
            return []
    
    def _extract_python_entities_line_based(self, content: str) -> List[Dict[str, Any]]:
        """基于行的Python实体提取（回退方案）"""
        entities = []
        lines = content.split("\n")
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("def "):
                # 函数定义
                match = re.match(r"def\s+(\w+)", stripped)
                if match:
                    entities.append({
                        "type": "function",
                        "name": match.group(1),
                        "line": i,
                        "start": i,
                        "end": self._find_entity_end(lines, i),
                    })
            elif stripped.startswith("class "):
                # 类定义
                match = re.match(r"class\s+(\w+)", stripped)
                if match:
                    entities.append({
                        "type": "class",
                        "name": match.group(1),
                        "line": i,
                        "start": i,
                        "end": self._find_entity_end(lines, i),
                    })
            elif stripped.startswith("async def "):
                # 异步函数定义
                match = re.match(r"async def\s+(\w+)", stripped)
                if match:
                    entities.append({
                        "type": "async_function",
                        "name": match.group(1),
                        "line": i,
                        "start": i,
                        "end": self._find_entity_end(lines, i),
                    })
        
        return entities

    def _find_entity_end(self, lines: List[str], start_line: int) -> int:
        """查找实体结束行"""
        if not lines or start_line >= len(lines):
            return start_line
            
        indent_level = 0
        # 计算起始行的缩进
        line = lines[start_line]
        indent_level = len(line) - len(line.lstrip())

        # 查找下一个相同或更少缩进的行
        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            if line.strip():  # 非空行
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level:
                    return i - 1

        return len(lines) - 1

    async def _update_entities(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        old_entities: List[Dict],
        new_entities: List[Dict],
    ) -> Dict[str, Any]:
        """逐实体更新"""
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")
        updated_lines = old_lines.copy()

        changes_made = 0

        for i, (old_entity, new_entity) in enumerate(zip(old_entities, new_entities)):
            old_start = old_entity["start"]
            old_end = old_entity["end"]
            new_start = new_entity["start"]
            new_end = new_entity["end"]

            # 提取实体内容
            old_entity_content = "\n".join(old_lines[old_start : old_end + 1])
            new_entity_content = "\n".join(new_lines[new_start : new_end + 1])

            # 如果实体内容不同,进行更新
            if old_entity_content != new_entity_content:
                # 替换实体内容
                updated_lines[old_start : old_end + 1] = new_lines[
                    new_start : new_end + 1
                ]
                changes_made += 1

        if changes_made > 0:
            # 写入更新后的内容
            updated_content = "\n".join(updated_lines)
            full_path.write_text(updated_content, encoding="utf-8")

            return {
                "success": True,
                "path": rel_path,
                "action": "smart_updated",
                "size": len(updated_content),
                "entities_updated": changes_made,
                "total_entities": len(old_entities),
                "message": f"智能更新 {rel_path}: 更新了 {changes_made}/{len(old_entities)} 个实体",
            }
        else:
            # 没有变化
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}",
            }
    
    async def _partial_entity_update(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        old_entities: List[Dict],
        new_entities: List[Dict],
    ) -> Dict[str, Any]:
        """部分实体更新（新实体是旧实体的子集）"""
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")
        updated_lines = old_lines.copy()
        
        changes_made = 0
        updated_entity_names = []
        
        # 创建名称到实体的映射
        old_entity_map = {e["name"]: e for e in old_entities}
        new_entity_map = {e["name"]: e for e in new_entities}
        
        # 更新匹配的实体
        for name, new_entity in new_entity_map.items():
            if name in old_entity_map:
                old_entity = old_entity_map[name]
                
                old_start = old_entity["start"]
                old_end = old_entity["end"]
                new_start = new_entity["start"]
                new_end = new_entity["end"]
                
                # 提取实体内容
                old_entity_content = "\n".join(old_lines[old_start:old_end + 1])
                new_entity_content = "\n".join(new_lines[new_start:new_end + 1])
                
                # 如果实体内容不同，进行更新
                if old_entity_content != new_entity_content:
                    updated_lines[old_start:old_end + 1] = new_lines[new_start:new_end + 1]
                    changes_made += 1
                    updated_entity_names.append(name)
        
        if changes_made > 0:
            # 写入更新后的内容
            updated_content = "\n".join(updated_lines)
            full_path.write_text(updated_content, encoding="utf-8")
            
            return {
                "success": True,
                "path": rel_path,
                "action": "partial_smart_updated",
                "size": len(updated_content),
                "entities_updated": changes_made,
                "updated_entities": updated_entity_names,
                "total_entities": len(old_entities),
                "message": f"部分智能更新 {rel_path}: 更新了 {changes_made}/{len(old_entities)} 个实体 ({', '.join(updated_entity_names)})",
            }
        else:
            # 没有变化
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}",
            }
    
    async def _name_based_entity_update(
        self,
        full_path: Path,
        new_content: str,
        rel_path: str,
        old_content: str,
        old_entities: List[Dict],
        new_entities: List[Dict],
    ) -> Dict[str, Any]:
        """基于名称的实体更新（尝试匹配名称）"""
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")
        updated_lines = old_lines.copy()
        
        changes_made = 0
        updated_entity_names = []
        unmatched_entities = []
        
        # 尝试匹配每个新实体
        for new_entity in new_entities:
            new_name = new_entity["name"]
            new_start = new_entity["start"]
            new_end = new_entity["end"]
            new_entity_content = "\n".join(new_lines[new_start:new_end + 1])
            
            # 查找匹配的旧实体
            matched = False
            for old_entity in old_entities:
                if old_entity["name"] == new_name:
                    old_start = old_entity["start"]
                    old_end = old_entity["end"]
                    old_entity_content = "\n".join(old_lines[old_start:old_end + 1])
                    
                    if old_entity_content != new_entity_content:
                        updated_lines[old_start:old_end + 1] = new_lines[new_start:new_end + 1]
                        changes_made += 1
                        updated_entity_names.append(new_name)
                    matched = True
                    break
            
            if not matched:
                unmatched_entities.append(new_name)
        
        if changes_made > 0:
            # 写入更新后的内容
            updated_content = "\n".join(updated_lines)
            full_path.write_text(updated_content, encoding="utf-8")
            
            message = f"名称匹配更新 {rel_path}: 更新了 {changes_made} 个实体"
            if updated_entity_names:
                message += f" ({', '.join(updated_entity_names)})"
            if unmatched_entities:
                message += f"，未匹配实体: {', '.join(unmatched_entities)}"
            
            return {
                "success": True,
                "path": rel_path,
                "action": "name_based_updated",
                "size": len(updated_content),
                "entities_updated": changes_made,
                "updated_entities": updated_entity_names,
                "unmatched_entities": unmatched_entities,
                "message": message,
            }
        elif unmatched_entities:
            # 有实体但都不匹配，使用差异更新
            print(f"🔍 有 {len(unmatched_entities)} 个实体无法匹配，使用差异更新")
            return await self._diff_based_update(full_path, new_content, rel_path, old_content)
        else:
            # 没有变化
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}",
            }

    async def _diff_based_update(
        self, full_path: Path, new_content: str, rel_path: str, old_content: str
    ) -> Dict[str, Any]:
        """基于差异的更新"""
        # 计算差异
        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="old",
                tofile="new",
                lineterm="",
            )
        )

        if not diff:
            # 没有差异
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}",
            }

        # 计算差异数量
        diff_count = len(
            [line for line in diff if line.startswith("+") or line.startswith("-")]
        )

        # 写入新内容
        full_path.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "path": rel_path,
            "action": "diff_updated",
            "size": len(new_content),
            "diff_count": diff_count,
            "diff_preview": "\n".join(diff[:10]),  # 只显示前10行差异
            "message": f"差异更新 {rel_path}: {diff_count} 处差异",
        }

    def _count_differences(self, old_content: str, new_content: str) -> int:
        """计算内容差异数量"""
        if old_content == new_content:
            return 0

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        diff_count = 0
        for old_line, new_line in zip(old_lines, new_lines):
            if old_line != new_line:
                diff_count += 1

        # 处理行数不同的情况
        diff_count += abs(len(old_lines) - len(new_lines))

        return diff_count

    async def patch_file(
        self, path: str, patch_content: str, **kwargs
    ) -> Dict[str, Any]:
        """
        使用补丁更新文件

        Args:
            path: 文件路径
            patch_content: 补丁内容(unified diff格式)

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            操作结果
        """
        try:
            full_path = self.project_path / path

            # 安全检查
            if self.safety_guard and not self.safety_guard.is_safe_path(full_path):
                return {"error": "访问路径超出项目范围"}

            # 检查文件是否存在
            if not full_path.exists():
                return {"error": f"文件不存在: {path}"}

            # 读取现有内容
            try:
                old_content = full_path.read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"读取文件失败: {str(e)}"}

            # 应用补丁
            try:
                patched_content = self._apply_patch(old_content, patch_content)
            except Exception as e:
                return {"error": f"应用补丁失败: {str(e)}"}

            # 写入更新后的内容
            full_path.write_text(patched_content, encoding="utf-8")

            return {
                "success": True,
                "path": path,
                "action": "patched",
                "size": len(patched_content),
                "message": f"应用补丁到文件: {path}",
            }

        except Exception as e:
            return {"error": f"补丁更新失败: {str(e)}"}

    def _apply_patch(self, old_content: str, patch_content: str) -> str:
        """应用unified diff补丁到内容"""
        # 对于补丁应用，使用简单方法：直接提取新文件内容
        # 因为完整的补丁应用逻辑很复杂且容易出错
        print("📝 使用简单补丁应用策略")
        return self._apply_simple_patch(old_content, patch_content)
    
    def _apply_simple_patch(self, old_content: str, patch_content: str) -> str:
        """简单补丁应用（回退方案）"""
        print("📝 使用简单补丁应用")
        
        # 尝试从补丁中重建新文件内容
        import re
        
        lines = patch_content.splitlines()
        old_lines = old_content.splitlines() if old_content else []
        
        # 解析hunk头部获取起始行号
        hunk_pattern = re.compile(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
        
        # 收集所有hunk信息
        hunks = []
        current_hunk = None
        
        for line in lines:
            # 跳过头部信息
            if line.startswith('---') or line.startswith('+++'):
                continue
            
            # 解析hunk头部
            match = hunk_pattern.match(line)
            if match:
                if current_hunk:
                    hunks.append(current_hunk)
                start_line = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                current_hunk = {
                    'old_start': start_line,
                    'old_count': old_count,
                    'content': []
                }
                continue
            
            # 收集hunk内容
            if current_hunk is not None:
                if line.startswith('-') or line.startswith('+') or line.startswith(' '):
                    current_hunk['content'].append(line)
                elif line:
                    # 非补丁内容行，可能是普通文本
                    current_hunk['content'].append(line)
        
        if current_hunk:
            hunks.append(current_hunk)
        
        if not hunks:
            # 无法解析hunk，使用旧逻辑
            print("⚠️  无法解析hunk，使用旧逻辑")
            new_content_lines = []
            in_hunk = False
            skip_headers = True
            
            for line in lines:
                if skip_headers and (line.startswith('---') or line.startswith('+++')):
                    continue
                elif skip_headers and line.startswith('@@'):
                    in_hunk = True
                    skip_headers = False
                    continue
                elif skip_headers:
                    continue
                
                if line.startswith('@@'):
                    in_hunk = True
                elif in_hunk:
                    if line.startswith(' '):
                        new_content_lines.append(line[1:])
                    elif line.startswith('+'):
                        new_content_lines.append(line[1:])
                    elif line.startswith('-'):
                        pass
                    else:
                        new_content_lines.append(line)
                else:
                    new_content_lines.append(line)
            
            if new_content_lines:
                result = '\n'.join(new_content_lines)
                if not result.endswith('\n'):
                    result += '\n'
                return result
            
            print("⚠️  无法解析补丁，返回原始内容")
            return old_content
        
        # 根据hunk信息重建文件
        result_lines = old_lines.copy()
        offset = 0  # 由于之前的修改导致的行偏移
        
        for hunk in hunks:
            old_start = hunk['old_start'] - 1  # 转换为0-based索引
            old_count = hunk['old_count']
            
            hunk_content = hunk['content']
            new_hunk_lines = []
            old_idx = 0
            
            for hunk_line in hunk_content:
                if hunk_line.startswith(' '):
                    # 上下文行
                    new_hunk_lines.append(('context', hunk_line[1:]))
                    old_idx += 1
                elif hunk_line.startswith('+'):
                    # 添加行
                    new_hunk_lines.append(('add', hunk_line[1:]))
                elif hunk_line.startswith('-'):
                    # 删除行
                    new_hunk_lines.append(('del', hunk_line[1:]))
                    old_idx += 1
            
            # 构建新的行列表
            insert_pos = old_start + offset
            lines_to_remove = 0
            lines_to_add = []
            
            for line_type, line_content in new_hunk_lines:
                if line_type == 'context':
                    lines_to_remove += 1
                    lines_to_add.append(line_content)
                elif line_type == 'add':
                    lines_to_add.append(line_content)
                elif line_type == 'del':
                    lines_to_remove += 1
            
            # 执行替换
            if insert_pos <= len(result_lines):
                result_lines[insert_pos:insert_pos + lines_to_remove] = lines_to_add
                offset += len(lines_to_add) - lines_to_remove
        
        result = '\n'.join(result_lines)
        if not result.endswith('\n') and result_lines:
            result += '\n'
        
        print(f"📝 简单补丁应用完成: 从{len(old_lines)}行 -> {len(result_lines)}行")
        return result

    async def get_file_diff(self, path: str, new_content: str) -> Dict[str, Any]:
        """
        获取文件差异

        Args:
            path: 文件路径
            new_content: 新内容

        Returns:
            差异信息
        """
        try:
            full_path = self.project_path / path

            # 安全检查
            if self.safety_guard and not self.safety_guard.is_safe_path(full_path):
                return {"error": "访问路径超出项目范围"}

            # 检查文件是否存在
            if not full_path.exists():
                return {
                    "success": True,
                    "path": path,
                    "action": "new_file",
                    "diff": f"新文件: {path}",
                    "message": "文件不存在,将创建新文件",
                }

            # 读取现有内容（尝试多种编码）
            old_content = None
            encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'gbk', 'gb2312']
            
            for encoding in encodings_to_try:
                try:
                    old_content = full_path.read_text(encoding=encoding)
                    print(f"📖 get_file_diff使用编码 {encoding} 成功读取文件")
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"⚠️  get_file_diff使用编码 {encoding} 读取失败: {str(e)}")
                    continue
            
            if old_content is None:
                return {"error": f"读取文件失败: 尝试了多种编码({', '.join(encodings_to_try)})均失败"}

            # 使用splitlines()获取行，不保留换行符
            old_lines = old_content.splitlines()
            new_lines = new_content.splitlines()
            
            # 计算差异
            diff = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=path,
                    tofile=path,
                    lineterm="",
                )
            )

            diff_count = len(
                [line for line in diff if line.startswith("+") or line.startswith("-")]
            )

            return {
                "success": True,
                "path": path,
                "diff_count": diff_count,
                "diff": "\n".join(diff),
                "old_size": len(old_content),
                "new_size": len(new_content),
                "message": f"文件差异: {diff_count} 处变化",
            }

        except Exception as e:
            return {"error": f"获取差异失败: {str(e)}"}

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
        
        # 记录参数来源
        param_source = "source_start_line/source_end_line"
        
        line_offset = 1  # 默认起始行号
        
        if start_line is not None or end_line is not None:
            # 转换为整数并自动调整行号
            
            try:
                start_line_val = 1
                end_line_val = len(lines)
                
                if start_line is not None:
                    start_line_val = int(start_line)
                    start_line_val = max(1, start_line_val)
                
                if end_line is not None:
                    end_line_val = int(end_line)
                    end_line_val = max(1, end_line_val)
                
                # 确保 start_line <= end_line
                if start_line_val > end_line_val:
                    start_line_val, end_line_val = end_line_val, start_line_val
                
                # 转换为0-based索引
                start = start_line_val - 1
                end = end_line_val
                
                # 边界检查
                start = max(0, min(start, len(lines)))
                end = max(start, min(end, len(lines)))
                
                lines = lines[start:end]
                line_offset = start_line_val
                print(f"📏 应用行范围过滤({param_source}): 第{start_line_val}-{end_line_val}行 → 实际第{start+1}-{end}行")
                
            except (ValueError, TypeError) as e:
                print(f"⚠️  行范围参数解析失败: {e}")
                # 继续使用所有行
                line_offset = 1
        
        # 应用正则表达式过滤 - 强制使用source_前缀参数
        pattern = kwargs.get('source_pattern')
        exclude_pattern = kwargs.get('source_exclude_pattern')
        
        # 检查是否使用了不带前缀的正则表达式参数
        if 'pattern' in kwargs or 'exclude_pattern' in kwargs:
            print(f"📝 信息：pattern/exclude_pattern参数被忽略（源文件过滤）")
            print(f"   如需正则表达式过滤，请使用source_pattern/source_exclude_pattern")
        
        if pattern or exclude_pattern:
            import re
            
            # 计算起始行号用于日志
            for i, line in enumerate(lines):
                line_num = line_offset + i
                
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
                   - 直接内容：如果source以"content:"开头，则提取后面的内容
                   - 文件内容：如果source以"file:"开头，则从文件读取
                   - 上下文文件名
                   - last_web_fetch等
            kwargs: 工具调用时的额外参数，支持以下过滤参数：
                   - source_start_line: 源文件起始行号（1-based，包含）- **必须使用**
                   - source_end_line: 源文件结束行号（1-based，包含）- **必须使用**
                   - source_pattern: 源文件正则表达式模式，只保留匹配的行 - **必须使用**
                   - source_exclude_pattern: 源文件正则表达式模式，排除匹配的行 - **必须使用**
        
        注意：当使用source参数时，所有源文件过滤参数必须使用source_前缀。
              使用不带前缀的参数将触发警告。
        
        Returns:
            内容字符串或None（如果无法获取）
        """
        try:
            print(f"🔍 incremental_update尝试从来源获取内容: {source}")
            
            # 方案1：直接内容（通过kwargs传递）
            if "direct_content" in kwargs:
                print(f"📝 使用直接传递的内容 ({len(kwargs['direct_content'])} 字符)")
                content = kwargs["direct_content"]
                return self._filter_content(content, kwargs)
            
            # 方案2：source包含直接内容
            if source.startswith("content:"):
                content = source[8:]  # 移除"content:"前缀
                print(f"📝 从source参数提取内容 ({len(content)} 字符)")
                return self._filter_content(content, kwargs)
            
            # 方案3：从文件读取
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
            
            # 方案4：从上下文文件读取
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
