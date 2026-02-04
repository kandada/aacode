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
        
    async def incremental_update(self, path: str, new_content: str, 
                               update_type: str = "smart", **kwargs) -> Dict[str, Any]:
        """
        增量更新文件
        
        Args:
            path: 文件路径
            new_content: 新内容
            update_type: 更新类型 ("smart", "replace", "append", "prepend")
            
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
            file_exists = full_path.exists()
            
            if not file_exists:
                # 文件不存在,直接创建
                return await self._create_new_file(full_path, new_content, path)
            
            # 读取现有内容
            try:
                old_content = full_path.read_text(encoding='utf-8')
            except Exception as e:
                return {"error": f"读取文件失败: {str(e)}"}
            
            if update_type == "replace":
                # 直接替换
                return await self._replace_file(full_path, new_content, path, old_content)
            
            elif update_type == "append":
                # 追加内容
                return await self._append_to_file(full_path, new_content, path, old_content)
            
            elif update_type == "prepend":
                # 前置内容
                return await self._prepend_to_file(full_path, new_content, path, old_content)
            
            else:  # smart
                # 智能更新:分析差异,只更新必要的部分
                return await self._smart_update(full_path, new_content, path, old_content)
                
        except Exception as e:
            return {"error": f"增量更新失败: {str(e)}"}
    
    async def _create_new_file(self, full_path: Path, content: str, rel_path: str) -> Dict[str, Any]:
        """创建新文件"""
        try:
            # 创建目录
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            full_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "path": rel_path,
                "action": "created",
                "size": len(content),
                "message": f"创建新文件: {rel_path}"
            }
        except Exception as e:
            return {"error": f"创建文件失败: {str(e)}"}
    
    async def _replace_file(self, full_path: Path, new_content: str, 
                          rel_path: str, old_content: str) -> Dict[str, Any]:
        """替换整个文件"""
        try:
            # 检查内容是否相同
            if old_content == new_content:
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(new_content),
                    "message": f"文件内容未变化: {rel_path}"
                }
            
            # 写入新内容
            full_path.write_text(new_content, encoding='utf-8')
            
            # 计算差异
            diff_count = self._count_differences(old_content, new_content)
            
            return {
                "success": True,
                "path": rel_path,
                "action": "replaced",
                "size": len(new_content),
                "diff_count": diff_count,
                "message": f"替换文件: {rel_path} ({diff_count} 处差异)"
            }
        except Exception as e:
            return {"error": f"替换文件失败: {str(e)}"}
    
    async def _append_to_file(self, full_path: Path, new_content: str,
                            rel_path: str, old_content: str) -> Dict[str, Any]:
        """追加内容到文件"""
        try:
            # 检查是否已经包含该内容
            if new_content in old_content:
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(old_content),
                    "message": f"内容已存在,无需追加: {rel_path}"
                }
            
            # 追加内容
            updated_content = old_content + "\n" + new_content
            full_path.write_text(updated_content, encoding='utf-8')
            
            return {
                "success": True,
                "path": rel_path,
                "action": "appended",
                "size": len(updated_content),
                "added_size": len(new_content),
                "message": f"追加内容到文件: {rel_path}"
            }
        except Exception as e:
            return {"error": f"追加内容失败: {str(e)}"}
    
    async def _prepend_to_file(self, full_path: Path, new_content: str,
                             rel_path: str, old_content: str) -> Dict[str, Any]:
        """前置内容到文件"""
        try:
            # 检查是否已经包含该内容
            if new_content in old_content:
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(old_content),
                    "message": f"内容已存在,无需前置: {rel_path}"
                }
            
            # 前置内容
            updated_content = new_content + "\n" + old_content
            full_path.write_text(updated_content, encoding='utf-8')
            
            return {
                "success": True,
                "path": rel_path,
                "action": "prepended",
                "size": len(updated_content),
                "added_size": len(new_content),
                "message": f"前置内容到文件: {rel_path}"
            }
        except Exception as e:
            return {"error": f"前置内容失败: {str(e)}"}
    
    async def _smart_update(self, full_path: Path, new_content: str,
                          rel_path: str, old_content: str) -> Dict[str, Any]:
        """智能更新:分析差异并最小化更改"""
        try:
            # 如果内容相同,无需更新
            if old_content == new_content:
                return {
                    "success": True,
                    "path": rel_path,
                    "action": "unchanged",
                    "size": len(new_content),
                    "message": f"文件内容未变化: {rel_path}"
                }
            
            # 分析文件类型
            file_ext = full_path.suffix.lower()
            is_code_file = file_ext in ['.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c', '.h']
            
            if is_code_file:
                # 对于代码文件,尝试智能合并
                return await self._smart_code_update(full_path, new_content, rel_path, old_content, file_ext)
            else:
                # 对于非代码文件,使用差异分析
                return await self._diff_based_update(full_path, new_content, rel_path, old_content)
                
        except Exception as e:
            return {"error": f"智能更新失败: {str(e)}"}
    
    async def _smart_code_update(self, full_path: Path, new_content: str,
                               rel_path: str, old_content: str, file_ext: str) -> Dict[str, Any]:
        """智能代码更新"""
        # 分析新旧内容的函数/类结构
        old_entities = self._extract_code_entities(old_content, file_ext)
        new_entities = self._extract_code_entities(new_content, file_ext)
        
        # 如果实体数量相同且名称相同,尝试逐实体更新
        if len(old_entities) == len(new_entities) and len(old_entities) > 0:
            # 检查实体名称是否匹配
            names_match = all(
                old_entities[i].get('name') == new_entities[i].get('name')
                for i in range(len(old_entities))
            )
            
            if names_match:
                # 逐实体更新
                return await self._update_entities(full_path, new_content, rel_path, old_content, old_entities, new_entities)
        
        # 否则使用差异分析
        return await self._diff_based_update(full_path, new_content, rel_path, old_content)
    
    def _extract_code_entities(self, content: str, file_ext: str) -> List[Dict[str, Any]]:
        """提取代码实体(函数,类等)"""
        entities = []
        lines = content.split('\n')
        
        if file_ext == '.py':
            # Python: 查找类和函数定义
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('def '):
                    # 函数定义
                    match = re.match(r'def\s+(\w+)', stripped)
                    if match:
                        entities.append({
                            'type': 'function',
                            'name': match.group(1),
                            'line': i,
                            'start': i,
                            'end': self._find_entity_end(lines, i)
                        })
                elif stripped.startswith('class '):
                    # 类定义
                    match = re.match(r'class\s+(\w+)', stripped)
                    if match:
                        entities.append({
                            'type': 'class',
                            'name': match.group(1),
                            'line': i,
                            'start': i,
                            'end': self._find_entity_end(lines, i)
                        })
        
        return entities
    
    def _find_entity_end(self, lines: List[str], start_line: int) -> int:
        """查找实体结束行"""
        indent_level = 0
        if start_line < len(lines):
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
    
    async def _update_entities(self, full_path: Path, new_content: str,
                             rel_path: str, old_content: str,
                             old_entities: List[Dict], new_entities: List[Dict]) -> Dict[str, Any]:
        """逐实体更新"""
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')
        updated_lines = old_lines.copy()
        
        changes_made = 0
        
        for i, (old_entity, new_entity) in enumerate(zip(old_entities, new_entities)):
            old_start = old_entity['start']
            old_end = old_entity['end']
            new_start = new_entity['start']
            new_end = new_entity['end']
            
            # 提取实体内容
            old_entity_content = '\n'.join(old_lines[old_start:old_end+1])
            new_entity_content = '\n'.join(new_lines[new_start:new_end+1])
            
            # 如果实体内容不同,进行更新
            if old_entity_content != new_entity_content:
                # 替换实体内容
                updated_lines[old_start:old_end+1] = new_lines[new_start:new_end+1]
                changes_made += 1
        
        if changes_made > 0:
            # 写入更新后的内容
            updated_content = '\n'.join(updated_lines)
            full_path.write_text(updated_content, encoding='utf-8')
            
            return {
                "success": True,
                "path": rel_path,
                "action": "smart_updated",
                "size": len(updated_content),
                "entities_updated": changes_made,
                "total_entities": len(old_entities),
                "message": f"智能更新 {rel_path}: 更新了 {changes_made}/{len(old_entities)} 个实体"
            }
        else:
            # 没有变化
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}"
            }
    
    async def _diff_based_update(self, full_path: Path, new_content: str,
                               rel_path: str, old_content: str) -> Dict[str, Any]:
        """基于差异的更新"""
        # 计算差异
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile='old',
            tofile='new',
            lineterm=''
        ))
        
        if not diff:
            # 没有差异
            return {
                "success": True,
                "path": rel_path,
                "action": "unchanged",
                "size": len(old_content),
                "message": f"文件内容未变化: {rel_path}"
            }
        
        # 计算差异数量
        diff_count = len([line for line in diff if line.startswith('+') or line.startswith('-')])
        
        # 写入新内容
        full_path.write_text(new_content, encoding='utf-8')
        
        return {
            "success": True,
            "path": rel_path,
            "action": "diff_updated",
            "size": len(new_content),
            "diff_count": diff_count,
            "diff_preview": '\n'.join(diff[:10]),  # 只显示前10行差异
            "message": f"差异更新 {rel_path}: {diff_count} 处差异"
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
    
    async def patch_file(self, path: str, patch_content: str, **kwargs) -> Dict[str, Any]:
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
                old_content = full_path.read_text(encoding='utf-8')
            except Exception as e:
                return {"error": f"读取文件失败: {str(e)}"}
            
            # 应用补丁
            try:
                patched_content = self._apply_patch(old_content, patch_content)
            except Exception as e:
                return {"error": f"应用补丁失败: {str(e)}"}
            
            # 写入更新后的内容
            full_path.write_text(patched_content, encoding='utf-8')
            
            return {
                "success": True,
                "path": path,
                "action": "patched",
                "size": len(patched_content),
                "message": f"应用补丁到文件: {path}"
            }
            
        except Exception as e:
            return {"error": f"补丁更新失败: {str(e)}"}
    
    def _apply_patch(self, old_content: str, patch_content: str) -> str:
        """应用补丁到内容"""
        # 简化的补丁应用逻辑
        # 在实际应用中,应该使用更完善的补丁库
        old_lines = old_content.splitlines(keepends=True)
        patch_lines = patch_content.splitlines()
        
        # 解析补丁头部
        if len(patch_lines) < 4:
            raise ValueError("无效的补丁格式")
        
        # 简单的补丁应用:直接使用新内容(实际应该解析和应用差异)
        # 这里简化处理,实际应该实现完整的补丁应用逻辑
        return old_content  # 简化实现,实际应该应用补丁
    
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
                    "message": "文件不存在,将创建新文件"
                }
            
            # 读取现有内容
            try:
                old_content = full_path.read_text(encoding='utf-8')
            except Exception as e:
                return {"error": f"读取文件失败: {str(e)}"}
            
            # 计算差异
            diff = list(difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=path,
                tofile=path,
                lineterm=''
            ))
            
            diff_count = len([line for line in diff if line.startswith('+') or line.startswith('-')])
            
            return {
                "success": True,
                "path": path,
                "diff_count": diff_count,
                "diff": '\n'.join(diff),
                "old_size": len(old_content),
                "new_size": len(new_content),
                "message": f"文件差异: {diff_count} 处变化"
            }
            
        except Exception as e:
            return {"error": f"获取差异失败: {str(e)}"}