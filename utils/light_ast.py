# 轻量Python AST工具 - 简化版
# utils/light_ast.py
"""
轻量Python AST工具，专为incremental_update设计
简化版本，专注于核心功能
"""

import ast
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field


@dataclass
class NodePosition:
    """节点位置信息"""
    line: int = 1
    col_offset: int = 0
    end_line: Optional[int] = None
    end_col_offset: Optional[int] = None
    
    def to_range(self) -> str:
        """转换为行范围字符串"""
        if self.end_line:
            return f"{self.line}-{self.end_line}"
        return str(self.line)


@dataclass
class ASTNode:
    """AST节点"""
    node_type: str
    position: NodePosition = field(default_factory=NodePosition)
    parent: Optional['ASTNode'] = None
    children: List['ASTNode'] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def add_child(self, child: 'ASTNode'):
        """添加子节点"""
        child.parent = self
        self.children.append(child)
    
    def find_nodes(self, node_type: str) -> List['ASTNode']:
        """查找指定类型的节点"""
        result = []
        if self.node_type == node_type:
            result.append(self)
        for child in self.children:
            result.extend(child.find_nodes(node_type))
        return result
    
    def find_node_at_line(self, line: int) -> Optional['ASTNode']:
        """查找指定行的节点"""
        if (self.position.line <= line and 
            (self.position.end_line is None or line <= self.position.end_line)):
            return self
        
        for child in self.children:
            found = child.find_node_at_line(line)
            if found:
                return found
        
        return None


class LightAST:
    """轻量Python AST工具"""
    
    def __init__(self):
        self.root: Optional[ASTNode] = None
        self.source_code: str = ""
        self.lines: List[str] = []
    
    def parse(self, code: str) -> ASTNode:
        """解析Python代码为AST"""
        self.source_code = code
        self.lines = code.split('\n')
        
        try:
            py_ast = ast.parse(code)
            self.root = self._convert_node(py_ast)
            return self.root
        except SyntaxError:
            # 返回空节点
            self.root = ASTNode(node_type="Module", position=NodePosition(line=1))
            return self.root
    
    def _convert_node(self, node: ast.AST, parent: Optional[ASTNode] = None) -> ASTNode:
        """转换AST节点"""
        position = NodePosition(
            line=getattr(node, 'lineno', 1),
            col_offset=getattr(node, 'col_offset', 0),
            end_line=getattr(node, 'end_lineno', None),
            end_col_offset=getattr(node, 'end_col_offset', None)
        )
        
        node_type = node.__class__.__name__
        ast_node = ASTNode(node_type=node_type, position=position, parent=parent)
        
        # 根据节点类型提取属性
        if isinstance(node, ast.Module):
            ast_node.attributes["body_count"] = len(node.body)
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.FunctionDef):
            ast_node.attributes.update({
                "name": node.name,
                "args": [arg.arg for arg in node.args.args],
                "decorators": [self._expr_to_str(d) for d in node.decorator_list],
                "returns": self._expr_to_str(node.returns) if node.returns else None
            })
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.ClassDef):
            ast_node.attributes.update({
                "name": node.name,
                "bases": [self._expr_to_str(base) for base in node.bases],
                "decorators": [self._expr_to_str(d) for d in node.decorator_list]
            })
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.Import):
            ast_node.attributes["names"] = [alias.name for alias in node.names]
        
        elif isinstance(node, ast.ImportFrom):
            ast_node.attributes.update({
                "module": node.module or "",
                "names": [alias.name for alias in node.names],
                "level": node.level
            })
        
        elif isinstance(node, ast.Assign):
            ast_node.attributes.update({
                "targets": [self._expr_to_str(target) for target in node.targets],
                "value": self._expr_to_str(node.value)
            })
        
        elif isinstance(node, ast.If):
            ast_node.attributes["test"] = self._expr_to_str(node.test)
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
            for child in node.orelse:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.For):
            ast_node.attributes.update({
                "target": self._expr_to_str(node.target),
                "iter": self._expr_to_str(node.iter)
            })
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.While):
            ast_node.attributes["test"] = self._expr_to_str(node.test)
            for child in node.body:
                child_node = self._convert_node(child, ast_node)
                ast_node.add_child(child_node)
        
        elif isinstance(node, ast.Return):
            ast_node.attributes["value"] = self._expr_to_str(node.value) if node.value else None
        
        elif isinstance(node, ast.Expr):
            ast_node.attributes["value"] = self._expr_to_str(node.value)
        
        elif isinstance(node, ast.Call):
            ast_node.attributes.update({
                "func": self._expr_to_str(node.func),
                "args": [self._expr_to_str(arg) for arg in node.args]
            })
        
        else:
            # 其他节点类型
            ast_node.attributes["repr"] = str(node)
        
        return ast_node
    
    def _expr_to_str(self, expr: ast.AST) -> str:
        """表达式转字符串"""
        if expr is None:
            return ""
        
        try:
            # 尝试获取源代码
            if hasattr(expr, 'lineno') and hasattr(expr, 'end_lineno'):
                start_line = expr.lineno - 1
                end_line = expr.end_lineno
                lines = self.lines[start_line:end_line]
                
                if len(lines) == 1:
                    start_col = expr.col_offset
                    end_col = expr.end_col_offset
                    return lines[0][start_col:end_col]
                else:
                    result_lines = []
                    for i, line in enumerate(lines):
                        if i == 0:
                            result_lines.append(line[expr.col_offset:])
                        elif i == len(lines) - 1:
                            result_lines.append(line[:expr.end_col_offset])
                        else:
                            result_lines.append(line)
                    return '\n'.join(result_lines)
            else:
                # 使用ast.unparse
                return ast.unparse(expr)
        except:
            return f"<{expr.__class__.__name__}>"
    
    def find_functions(self) -> List[ASTNode]:
        """查找所有函数"""
        if not self.root:
            return []
        return self.root.find_nodes("FunctionDef") + self.root.find_nodes("AsyncFunctionDef")
    
    def find_classes(self) -> List[ASTNode]:
        """查找所有类"""
        if not self.root:
            return []
        return self.root.find_nodes("ClassDef")
    
    def find_imports(self) -> List[ASTNode]:
        """查找所有导入"""
        if not self.root:
            return []
        return self.root.find_nodes("Import") + self.root.find_nodes("ImportFrom")
    
    def find_node_at_line(self, line: int) -> Optional[ASTNode]:
        """查找指定行的节点"""
        if not self.root:
            return None
        return self.root.find_node_at_line(line)
    
    def get_code_slice(self, start_line: int, end_line: int) -> str:
        """获取代码片段"""
        if not self.lines:
            return ""
        
        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.lines), end_line)
        
        return '\n'.join(self.lines[start_idx:end_idx])
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        if not self.root:
            return {}
        
        return self._node_to_dict(self.root)
    
    def _node_to_dict(self, node: ASTNode) -> Dict[str, Any]:
        """节点转字典"""
        result = {
            "type": node.node_type,
            "position": {
                "line": node.position.line,
                "end_line": node.position.end_line,
                "range": node.position.to_range()
            },
            "attributes": node.attributes
        }
        
        if node.children:
            result["children"] = [self._node_to_dict(child) for child in node.children]
        
        return result


class IncrementalASTHelper:
    """增量AST助手，与incremental_tools.py集成"""
    
    @staticmethod
    def analyze_for_update(code: str, update_type: str, **kwargs) -> Dict[str, Any]:
        """
        分析代码以进行增量更新
        
        Args:
            code: 源代码
            update_type: 更新类型
            **kwargs: 更新参数
            
        Returns:
            分析结果
        """
        ast_tool = LightAST()
        ast_tool.parse(code)
        
        result = {
            "ast_available": True,
            "functions": [],
            "classes": [],
            "imports": [],
            "suggestions": []
        }
        
        # 收集函数信息
        for func in ast_tool.find_functions():
            result["functions"].append(func.attributes.get("name", "unnamed"))
        
        # 收集类信息
        for cls in ast_tool.find_classes():
            result["classes"].append(cls.attributes.get("name", "unnamed"))
        
        # 收集导入信息
        for imp in ast_tool.find_imports():
            if imp.node_type == "Import":
                result["imports"].extend(imp.attributes.get("names", []))
            elif imp.node_type == "ImportFrom":
                module = imp.attributes.get("module", "")
                names = imp.attributes.get("names", [])
                result["imports"].extend([f"{module}.{name}" for name in names])
        
        # 根据更新类型提供建议
        line_number = kwargs.get("line_number")
        line_range = kwargs.get("line_range")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        
        if update_type == "line_update" and line_number:
            node = ast_tool.find_node_at_line(line_number)
            if node:
                result["target_node"] = {
                    "type": node.node_type,
                    "position": node.position.to_range()
                }
                result["suggestions"].append(f"将在{node.node_type}节点处更新")
        
        elif update_type == "replace" and start_line and end_line:
            result["line_range"] = f"{start_line}-{end_line}"
            # 分析范围内的节点
            nodes_in_range = []
            for line in range(start_line, end_line + 1):
                node = ast_tool.find_node_at_line(line)
                if node and node not in nodes_in_range:
                    nodes_in_range.append(node)
            
            if nodes_in_range:
                result["nodes_in_range"] = [
                    {"type": n.node_type, "position": n.position.to_range()}
                    for n in nodes_in_range
                ]
                result["suggestions"].append(f"替换范围内包含{len(nodes_in_range)}个AST节点")
        
        return result
    
    @staticmethod
    def validate_update(code: str, new_code: str, update_type: str, **kwargs) -> Dict[str, Any]:
        """
        验证更新
        
        Args:
            code: 原始代码
            new_code: 新代码
            update_type: 更新类型
            **kwargs: 更新参数
            
        Returns:
            验证结果
        """
        result = {
            "valid": True,
            "warnings": [],
            "errors": []
        }
        
        # 基本验证
        if not code.strip():
            result["warnings"].append("原始代码为空")
        
        if not new_code.strip() and update_type != "delete":
            result["warnings"].append("新代码为空")
        
        # 行号验证
        line_number = kwargs.get("line_number")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        
        if line_number is not None and line_number < 1:
            result["errors"].append(f"无效的行号: {line_number}")
            result["valid"] = False
        
        if start_line is not None and start_line < 1:
            result["errors"].append(f"无效的起始行: {start_line}")
            result["valid"] = False
        
        if end_line is not None and end_line < 1:
            result["errors"].append(f"无效的结束行: {end_line}")
            result["valid"] = False
        
        if start_line is not None and end_line is not None and start_line > end_line:
            result["errors"].append(f"起始行({start_line})大于结束行({end_line})")
            result["valid"] = False
        
        # 行范围验证
        line_range = kwargs.get("line_range")
        if line_range:
            if '-' in line_range:
                try:
                    start, end = map(int, line_range.split('-'))
                    if start < 1 or end < 1 or start > end:
                        result["errors"].append(f"无效的行范围: {line_range}")
                        result["valid"] = False
                except ValueError:
                    result["errors"].append(f"无法解析行范围: {line_range}")
                    result["valid"] = False
        
        # 语法验证
        if update_type == "replace" and not (start_line or end_line or line_range):
            try:
                ast.parse(new_code)
            except SyntaxError as e:
                result["warnings"].append(f"新代码语法错误: {e}")
        
        return result
    
    @staticmethod
    def generate_update_plan(code: str, update_type: str, **kwargs) -> Dict[str, Any]:
        """
        生成更新计划
        
        Args:
            code: 原始代码
            update_type: 更新类型
            **kwargs: 更新参数
            
        Returns:
            更新计划
        """
        # 验证更新
        validation = IncrementalASTHelper.validate_update(
            code, 
            kwargs.get("new_content", ""), 
            update_type, 
            **kwargs
        )
        
        if not validation["valid"]:
            return {
                "plan_available": False,
                "errors": validation["errors"],
                "warnings": validation["warnings"]
            }
        
        # 分析代码
        analysis = IncrementalASTHelper.analyze_for_update(code, update_type, **kwargs)
        
        # 创建计划
        plan = {
            "plan_available": True,
            "update_type": update_type,
            "parameters": kwargs,
            "ast_analysis": analysis,
            "steps": []
        }
        
        # 根据更新类型添加步骤
        if update_type == "line_update":
            line_number = kwargs.get("line_number")
            line_range = kwargs.get("line_range")
            
            if line_number:
                plan["steps"].append({
                    "action": "update_line",
                    "line": line_number,
                    "description": f"更新第{line_number}行"
                })
        
        elif update_type == "replace":
            start_line = kwargs.get("start_line")
            end_line = kwargs.get("end_line")
            
            if start_line and end_line:
                plan["steps"].append({
                    "action": "replace_range",
                    "start": start_line,
                    "end": end_line,
                    "description": f"替换{start_line}-{end_line}行"
                })
            else:
                plan["steps"].append({
                    "action": "replace_file",
                    "description": "替换整个文件"
                })
        
        elif update_type == "insert_before":
            line_number = kwargs.get("line_number")
            if line_number:
                plan["steps"].append({
                    "action": "insert_before_line",
                    "line": line_number,
                    "description": f"在第{line_number}行之前插入"
                })
        
        elif update_type == "insert_after":
            line_number = kwargs.get("line_number")
            if line_number:
                plan["steps"].append({
                    "action": "insert_after_line",
                    "line": line_number,
                    "description": f"在第{line_number}行之后插入"
                })
        
        elif update_type == "append":
            plan["steps"].append({
                "action": "append_to_file",
                "description": "追加到文件末尾"
            })
        
        elif update_type == "prepend":
            plan["steps"].append({
                "action": "prepend_to_file",
                "description": "插入到文件开头"
            })
        
        return plan


# 工具函数
def create_light_ast() -> LightAST:
    """创建轻量AST实例"""
    return LightAST()

def analyze_code_structure(code: str) -> Dict[str, Any]:
    """分析代码结构"""
    ast_tool = LightAST()
    root = ast_tool.parse(code)
    
    functions = []
    for func in ast_tool.find_functions():
        functions.append({
            "name": func.attributes.get("name", "unnamed"),
            "args": func.attributes.get("args", []),
            "line": func.position.line
        })
    
    classes = []
    for cls in ast_tool.find_classes():
        classes.append({
            "name": cls.attributes.get("name", "unnamed"),
            "bases": cls.attributes.get("bases", []),
            "line": cls.position.line
        })
    
    imports = []
    for imp in ast_tool.find_imports():
        if imp.node_type == "Import":
            imports.append({
                "type": "import",
                "names": imp.attributes.get("names", [])
            })
        elif imp.node_type == "ImportFrom":
            imports.append({
                "type": "import_from",
                "module": imp.attributes.get("module", ""),
                "names": imp.attributes.get("names", [])
            })
    
    return {
        "success": root is not None,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "ast_summary": {
            "node_count": len(root.children) if root else 0,
            "max_depth": 3  # 简化版本，固定深度
        }
    }


def get_ast_analysis_for_incremental_update(code: str, **kwargs) -> Dict[str, Any]:
    """
    为增量更新获取AST分析
    
    Args:
        code: 源代码
        **kwargs: 更新参数
        
    Returns:
        AST分析结果
    """
    update_type = kwargs.pop("update_type", "smart")
    return IncrementalASTHelper.analyze_for_update(code, update_type, **kwargs)