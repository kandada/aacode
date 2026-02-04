# 代码智能分析工具
# utils/code_analyzer.py
"""
代码智能分析工具，用于代码质量检查和增量更新
"""
import ast
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import difflib


@dataclass
class CodeIssue:
    """代码问题"""
    type: str  # style, security, performance, logic
    severity: str  # low, medium, high, critical
    line: int
    column: int
    message: str
    suggestion: str


@dataclass
class CodeChange:
    """代码变化"""
    type: str  # add, remove, modify
    line_number: int
    old_content: str
    new_content: str
    description: str


@dataclass
class AnalysisResult:
    """分析结果"""
    functions: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]
    imports: List[str]
    complexity_score: float
    issues: List[CodeIssue]
    lines_of_code: int


class CodeAnalyzer:
    """代码分析器"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.analysis_cache = {}
    
    def analyze_file(self, file_path: Path) -> AnalysisResult:
        """分析单个文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self.analyze_code(content, file_path.suffix)
        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return AnalysisResult([], [], [], 0, [], 0)
    
    def analyze_code(self, code: str, file_extension: str = '.py') -> AnalysisResult:
        """分析代码"""
        if file_extension == '.py':
            return self._analyze_python(code)
        else:
            return self._analyze_generic(code)
    
    def _analyze_python(self, code: str) -> AnalysisResult:
        """分析Python代码"""
        try:
            tree = ast.parse(code)
            
            # 分析函数
            functions = []
            classes = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        'name': node.name,
                        'line': node.lineno,
                        'args': [arg.arg for arg in node.args.args],
                        'decorators': [str(d) for d in node.decorator_list]
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        'name': node.name,
                        'line': node.lineno,
                        'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    })
                elif isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    imports.extend([f"{module}.{alias.name}" for alias in node.names])
            
            # 计算复杂度
            complexity_score = self._calculate_complexity(tree)
            
            # 检查问题
            issues = self._check_python_issues(code, tree)
            
            # 计算代码行数
            lines_of_code = len([line for line in code.split('\n') if line.strip()])
            
            return AnalysisResult(
                functions=functions,
                classes=classes,
                imports=imports,
                complexity_score=complexity_score,
                issues=issues,
                lines_of_code=lines_of_code
            )
            
        except SyntaxError as e:
            return AnalysisResult([], [], [], 0, [
                CodeIssue('syntax', 'critical', e.lineno or 0, 0, str(e), "修复语法错误")
            ], 0)
    
    def _analyze_generic(self, code: str) -> AnalysisResult:
        """分析通用代码"""
        lines = code.split('\n')
        lines_of_code = len([line for line in lines if line.strip()])
        
        # 简单的通用分析
        issues = []
        
        # 检查长行
        for i, line in enumerate(lines):
            if len(line) > 120:
                issues.append(CodeIssue(
                    'style', 'low', i+1, 0,
                    '行过长', '考虑将长行拆分为多行'
                ))
        
        return AnalysisResult([], [], [], 1.0, issues, lines_of_code)
    
    def _calculate_complexity(self, tree: ast.AST) -> float:
        """计算代码复杂度"""
        complexity = 1.0  # 基础复杂度
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.With)):
                complexity += 1
            elif isinstance(node, ast.Try):
                complexity += 1.5
            elif isinstance(node, ast.ListComp) or isinstance(node, ast.DictComp):
                complexity += 0.5
            elif isinstance(node, ast.Lambda):
                complexity += 0.5
        
        return complexity
    
    def _check_python_issues(self, code: str, tree: ast.AST) -> List[CodeIssue]:
        """检查Python代码问题"""
        issues = []
        lines = code.split('\n')
        
        # 检查常见问题
        for i, line in enumerate(lines):
            # 检查TODO/FIXME
            if 'TODO' in line or 'FIXME' in line:
                issues.append(CodeIssue(
                    'style', 'low', i+1, 0,
                    '包含未完成的TODO/FIXME', '完成或移除TODO标记'
                ))
            
            # 检查调试代码
            if 'print(' in line and not line.strip().startswith('#'):
                issues.append(CodeIssue(
                    'style', 'medium', i+1, 0,
                    '包含调试打印语句', '使用日志系统替代print'
                ))
            
            # 检查裸except
            if 'except:' in line or 'except :' in line:
                issues.append(CodeIssue(
                    'style', 'high', i+1, 0,
                    '使用裸except子句', '指定具体的异常类型'
                ))
        
        # AST分析
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 检查函数长度
                if hasattr(node, 'end_lineno') and node.end_lineno:
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > 80:
                        issues.append(CodeIssue(
                            'performance', 'medium', node.lineno, 0,
                            f'函数过长 ({func_lines}行)', '考虑拆分为更小的函数'
                        ))
                
                # 检查参数数量
                if len(node.args.args) > 7:
                    issues.append(CodeIssue(
                        'style', 'medium', node.lineno, 0,
                        f'参数过多 ({len(node.args.args)}个)', '考虑使用配置对象或减少参数'
                    ))
        
        return issues
    
    def analyze_changes(self, old_code: str, new_code: str) -> List[CodeChange]:
        """分析代码变化"""
        changes = []
        
        # 使用difflib比较代码
        old_lines = old_code.split('\n')
        new_lines = new_code.split('\n')
        
        differ = difflib.unified_diff(
            old_lines, new_lines,
            fromfile='old', tofile='new',
            lineterm='', n=3
        )
        
        current_change = None
        
        for line in differ:
            if line.startswith('@@'):
                # 新的变化块
                continue
            elif line.startswith('---') or line.startswith('+++'):
                # 文件头
                continue
            elif line.startswith('-'):
                # 删除的行
                if current_change and current_change.type != 'remove':
                    changes.append(current_change)
                current_change = CodeChange(
                    type='remove',
                    line_number=0,  # 需要从上下文计算
                    old_content=line[1:],
                    new_content='',
                    description='删除代码行'
                )
            elif line.startswith('+'):
                # 添加的行
                if current_change and current_change.type != 'add':
                    changes.append(current_change)
                current_change = CodeChange(
                    type='add',
                    line_number=0,
                    old_content='',
                    new_content=line[1:],
                    description='添加代码行'
                )
            else:
                # 上下文行，结束当前变化
                if current_change:
                    changes.append(current_change)
                    current_change = None
        
        if current_change:
            changes.append(current_change)
        
        return changes
    
    def analyze_complexity(self, code: str) -> Dict[str, float]:
        """分析代码复杂度"""
        try:
            tree = ast.parse(code)
            
            # 不同类型的复杂度指标
            cyclomatic = self._calculate_complexity(tree)
            
            # 认知复杂度（简化版）
            cognitive = self._calculate_cognitive_complexity(tree)
            
            # 嵌套深度
            nesting_depth = self._calculate_nesting_depth(tree)
            
            return {
                'cyclomatic': cyclomatic,
                'cognitive': cognitive,
                'nesting_depth': nesting_depth,
                'overall': (cyclomatic + cognitive + nesting_depth) / 3
            }
            
        except SyntaxError:
            return {
                'cyclomatic': 0.0,
                'cognitive': 0.0,
                'nesting_depth': 0.0,
                'overall': 0.0
            }
    
    def _calculate_cognitive_complexity(self, tree: ast.AST) -> float:
        """计算认知复杂度（简化版）"""
        complexity = 0.0
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += 0.5
        
        return complexity
    
    def _calculate_nesting_depth(self, tree: ast.AST) -> float:
        """计算嵌套深度"""
        max_depth = 0
        
        def _visit_node(node: ast.AST, depth: int = 0):
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.With, ast.Try)):
                    _visit_node(child, depth + 1)
                else:
                    _visit_node(child, depth)
        
        _visit_node(tree)
        return max_depth
    
    def suggest_improvements(self, analysis: AnalysisResult) -> List[str]:
        """建议改进"""
        suggestions = []
        
        # 基于复杂度的建议
        if analysis.complexity_score > 10:
            suggestions.append("代码复杂度较高，建议拆分为更小的函数")
        
        # 基于问题的建议
        critical_issues = [i for i in analysis.issues if i.severity == 'critical']
        if critical_issues:
            suggestions.append(f"发现{len(critical_issues)}个严重问题，需要立即修复")
        
        high_issues = [i for i in analysis.issues if i.severity == 'high']
        if high_issues:
            suggestions.append(f"发现{len(high_issues)}个高优先级问题")
        
        # 基于代码结构的建议
        if not analysis.functions and not analysis.classes:
            suggestions.append("考虑将代码组织为函数或类")
        
        return suggestions
    
    def check_code_quality(self, code: str, file_extension: str = '.py') -> List[CodeIssue]:
        """检查代码质量"""
        analysis = self.analyze_code(code, file_extension)
        return analysis.issues
    
    def get_quality_score(self, analysis: AnalysisResult) -> float:
        """获取代码质量评分"""
        base_score = 100.0
        
        # 根据复杂度扣分
        complexity_penalty = min(analysis.complexity_score * 2, 30)
        
        # 根据问题扣分
        issue_penalty = 0
        for issue in analysis.issues:
            severity_weights = {
                'low': 1,
                'medium': 3,
                'high': 5,
                'critical': 10
            }
            issue_penalty += severity_weights.get(issue.severity, 1)
        
        # 计算最终得分
        final_score = max(0, base_score - complexity_penalty - issue_penalty)
        
        return final_score