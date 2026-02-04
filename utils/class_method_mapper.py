#!/usr/bin/env python3
"""
类方法映射工具
用于分析项目目录中的类和函数结构，生成class_method_map.md
支持多语言项目分析和增强功能
"""
import ast
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import re
from datetime import datetime


class ClassMethodMapper:
    """类方法映射器，用于提取项目中的类和函数结构"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.class_map: Dict[str, Dict] = {}
        self.function_map: Dict[str, Dict] = {}
        self.imports_map: Dict[str, List] = {}
        self.file_structure: Dict[str, List] = {}
        
    def analyze_project(self) -> Dict[str, Any]:
        """分析整个项目"""
        print(f"🔍 开始分析项目结构: {self.project_path}")
        
        # 清空之前的分析结果
        self.class_map.clear()
        self.function_map.clear()
        self.imports_map.clear()
        self.file_structure.clear()
        
        # 查找所有Python文件
        python_files = list(self.project_path.rglob("*.py"))
        
        print(f"📁 找到 {len(python_files)} 个Python文件")
        
        analyzed_count = 0
        for file_path in python_files:
            # 跳过虚拟环境目录和缓存目录
            if any(skip in str(file_path) for skip in ['.venv', '__pycache__', '.git', '.aacode']):
                continue
                
            try:
                self._analyze_file(file_path)
                analyzed_count += 1
            except Exception as e:
                print(f"⚠️  分析文件 {file_path.relative_to(self.project_path)} 时出错: {e}")
        
        print(f"✅ 成功分析 {analyzed_count} 个文件")
        return self._generate_summary()
    
    def _analyze_file(self, file_path: Path):
        """分析单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            relative_path = file_path.relative_to(self.project_path)
            file_key = str(relative_path)
            
            # 记录文件结构
            self.file_structure[file_key] = []
            
            # 分析导入
            imports = self._extract_imports(tree)
            if imports:
                self.imports_map[file_key] = imports
            
            # 分析类和函数
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = self._analyze_class(node, file_key, content)
                    self.file_structure[file_key].append({
                        'type': 'class',
                        'name': class_info['name'],
                        'line': class_info['line']
                    })
                elif isinstance(node, ast.FunctionDef):
                    # 检查是否是类方法
                    parent = self._get_parent(node, tree)
                    if not isinstance(parent, ast.ClassDef):
                        func_info = self._analyze_function(node, file_key, content)
                        self.file_structure[file_key].append({
                            'type': 'function',
                            'name': func_info['name'],
                            'line': func_info['line']
                        })
                    
        except SyntaxError as e:
            print(f"⚠️  文件 {file_path.relative_to(self.project_path)} 语法错误: {e}")
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                content = file_path.read_text(encoding='gbk')
                self._analyze_file_content(content, file_path)
            except:
                print(f"⚠️  无法解析文件 {file_path.relative_to(self.project_path)} 的编码")
    
    def _analyze_file_content(self, content: str, file_path: Path):
        """分析文件内容"""
        tree = ast.parse(content)
        relative_path = file_path.relative_to(self.project_path)
        file_key = str(relative_path)
        
        # 分析类和函数
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._analyze_class(node, file_key, content)
            elif isinstance(node, ast.FunctionDef):
                parent = self._get_parent(node, tree)
                if not isinstance(parent, ast.ClassDef):
                    self._analyze_function(node, file_key, content)
    
    def _extract_imports(self, tree: ast.AST) -> List[Dict]:
        """提取导入语句"""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        'type': 'import',
                        'module': alias.name,
                        'alias': alias.asname,
                        'lineno': node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    imports.append({
                        'type': 'from_import',
                        'module': module,
                        'name': alias.name,
                        'alias': alias.asname,
                        'lineno': node.lineno
                    })
        
        return imports
    
    def _analyze_class(self, node: ast.ClassDef, file_key: str, content: str) -> Dict:
        """分析类定义"""
        class_name = node.name
        full_class_name = f"{file_key}:{class_name}"
        
        # 提取基类
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attr_name(base))
        
        # 提取类文档字符串
        docstring = ast.get_docstring(node)
        
        # 提取方法
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = self._extract_method_info(item, content)
                methods.append(method_info)
        
        # 提取类装饰器
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(self._get_decorator_name(decorator))
        
        # 提取类属性
        attributes = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append({
                            'name': target.id,
                            'line': item.lineno
                        })
        
        class_info = {
            'name': class_name,
            'file': file_key,
            'line': node.lineno,
            'bases': bases,
            'docstring': docstring or '',
            'methods': methods,
            'attributes': attributes,
            'decorators': decorators,
            'full_name': full_class_name
        }
        
        self.class_map[full_class_name] = class_info
        return class_info
    
    def _analyze_function(self, node: ast.FunctionDef, file_key: str, content: str) -> Dict:
        """分析函数定义"""
        function_name = node.name
        full_function_name = f"{file_key}:{function_name}"
        
        function_info = self._extract_function_info(node, content)
        function_info.update({
            'name': function_name,
            'file': file_key,
            'line': node.lineno,
            'full_name': full_function_name
        })
        
        self.function_map[full_function_name] = function_info
        return function_info
    
    def _extract_method_info(self, node: ast.FunctionDef, content: str) -> Dict:
        """提取方法信息"""
        info = self._extract_function_info(node, content)
        info['name'] = node.name
        return info
    
    def _extract_function_info(self, node: ast.FunctionDef, content: str) -> Dict:
        """提取函数/方法信息"""
        # 提取参数
        args = []
        
        # 位置参数
        for arg in node.args.args:
            args.append(arg.arg)
        
        # 提取默认参数
        defaults = []
        for default in node.args.defaults:
            try:
                defaults.append(ast.unparse(default) if hasattr(ast, 'unparse') else str(default))
            except:
                defaults.append(str(default))
        
        # 提取文档字符串
        docstring = ast.get_docstring(node)
        
        # 提取返回类型注解
        returns = None
        if node.returns:
            try:
                returns = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
            except:
                returns = str(node.returns)
        
        # 提取装饰器
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(self._get_decorator_name(decorator))
        
        return {
            'args': args,
            'defaults': defaults,
            'docstring': docstring or '',
            'returns': returns,
            'decorators': decorators,
            'is_async': isinstance(node, ast.AsyncFunctionDef)
        }
    
    def _get_attr_name(self, node: ast.Attribute) -> str:
        """获取属性名称"""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attr_name(node.value)}.{node.attr}"
        else:
            return node.attr
    
    def _get_decorator_name(self, node: ast.AST) -> str:
        """获取装饰器名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attr_name(node)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return self._get_attr_name(node.func)
        return str(node)
    
    def _get_parent(self, node: ast.AST, tree: ast.AST) -> Optional[ast.AST]:
        """获取节点的父节点"""
        # 简单的父节点查找
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                if child is node:
                    return parent
        return None
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成分析摘要"""
        return {
            'project_path': str(self.project_path),
            'class_count': len(self.class_map),
            'function_count': len(self.function_map),
            'file_count': len(self.file_structure),
            'classes': list(self.class_map.keys()),
            'functions': list(self.function_map.keys()),
            'file_structure': self.file_structure
        }
    
    def generate_class_method_map(self) -> str:
        """生成类方法映射的Markdown文档"""
        lines = []
        
        lines.append("# 项目类方法映射")
        lines.append("")
        lines.append(f"项目路径: `{self.project_path}`")
        lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"类数量: {len(self.class_map)}")
        lines.append(f"函数数量: {len(self.function_map)}")
        lines.append(f"文件数量: {len(self.file_structure)}")
        lines.append("")
        
        # 文件结构概览
        lines.append("## 文件结构概览")
        lines.append("")
        
        for file_path, items in sorted(self.file_structure.items()):
            class_count = sum(1 for item in items if item['type'] == 'class')
            function_count = sum(1 for item in items if item['type'] == 'function')
            
            lines.append(f"- `{file_path}`")
            lines.append(f"  - 类: {class_count} 个")
            lines.append(f"  - 函数: {function_count} 个")
        lines.append("")
        
        # 按文件分组显示类
        files_with_classes = {}
        for class_name, class_info in self.class_map.items():
            file_path = class_info['file']
            if file_path not in files_with_classes:
                files_with_classes[file_path] = []
            files_with_classes[file_path].append(class_info)
        
        if files_with_classes:
            lines.append("## 类定义详情")
            lines.append("")
            
            for file_path, classes in sorted(files_with_classes.items()):
                lines.append(f"### 文件: `{file_path}`")
                lines.append("")
                
                for class_info in sorted(classes, key=lambda x: x['line']):
                    lines.append(f"#### 类: `{class_info['name']}`")
                    lines.append("")
                    
                    # 基本信息
                    lines.append(f"- **位置**: 第 {class_info['line']} 行")
                    
                    if class_info['bases']:
                        bases_str = ', '.join([f"`{base}`" for base in class_info['bases']])
                        lines.append(f"- **继承自**: {bases_str}")
                    
                    if class_info['decorators']:
                        decorators_str = ', '.join([f"`{dec}`" for dec in class_info['decorators']])
                        lines.append(f"- **装饰器**: {decorators_str}")
                    
                    if class_info['docstring']:
                        doc_preview = class_info['docstring'].split('\n')[0][:100]
                        lines.append(f"- **文档**: {doc_preview}...")
                    
                    # 属性
                    if class_info['attributes']:
                        lines.append("- **属性**:")
                        for attr in class_info['attributes']:
                            lines.append(f"  - `{attr['name']}` (第 {attr['line']} 行)")
                    
                    # 方法
                    if class_info['methods']:
                        lines.append("- **方法**:")
                        for method in class_info['methods']:
                            args_str = ', '.join(method['args'])
                            method_desc = f"`{method['name']}({args_str})`"
                            if method['is_async']:
                                method_desc = f"`async {method_desc}`"
                            if method['decorators']:
                                decorators = ', '.join([f"@{dec}" for dec in method['decorators']])
                                method_desc = f"{decorators} {method_desc}"
                            lines.append(f"  - {method_desc}")
                    
                    lines.append("")
        
        # 按文件分组显示函数
        files_with_functions = {}
        for func_name, func_info in self.function_map.items():
            file_path = func_info['file']
            if file_path not in files_with_functions:
                files_with_functions[file_path] = []
            files_with_functions[file_path].append(func_info)
        
        if files_with_functions:
            lines.append("## 函数定义详情")
            lines.append("")
            
            for file_path, functions in sorted(files_with_functions.items()):
                lines.append(f"### 文件: `{file_path}`")
                lines.append("")
                
                for func_info in sorted(functions, key=lambda x: x['line']):
                    lines.append(f"#### 函数: `{func_info['name']}`")
                    lines.append("")
                    
                    # 基本信息
                    lines.append(f"- **位置**: 第 {func_info['line']} 行")
                    
                    args_str = ', '.join(func_info['args'])
                    lines.append(f"- **参数**: `({args_str})`")
                    
                    if func_info['returns']:
                        lines.append(f"- **返回类型**: `{func_info['returns']}`")
                    
                    if func_info['decorators']:
                        decorators_str = ', '.join([f"`{dec}`" for dec in func_info['decorators']])
                        lines.append(f"- **装饰器**: {decorators_str}")
                    
                    if func_info['is_async']:
                        lines.append("- **类型**: `async` 函数")
                    
                    if func_info['docstring']:
                        doc_preview = func_info['docstring'].split('\n')[0][:100]
                        lines.append(f"- **文档**: {doc_preview}...")
                    
                    lines.append("")
        
        # 导入关系
        if self.imports_map:
            lines.append("## 导入关系")
            lines.append("")
            
            for file_path, imports in sorted(self.imports_map.items()):
                if imports:
                    lines.append(f"### `{file_path}`")
                    lines.append("")
                    
                    for imp in imports:
                        if imp['type'] == 'import':
                            if imp['alias']:
                                lines.append(f"- `import {imp['module']} as {imp['alias']}`")
                            else:
                                lines.append(f"- `import {imp['module']}`")
                        else:  # from_import
                            if imp['alias']:
                                lines.append(f"- `from {imp['module']} import {imp['name']} as {imp['alias']}`")
                            else:
                                lines.append(f"- `from {imp['module']} import {imp['name']}`")
                    
                    lines.append("")
        
        return '\n'.join(lines)
    
    def save_class_method_map(self, output_file: str = "class_method_map.md") -> Path:
        """保存类方法映射到文件"""
        content = self.generate_class_method_map()
        output_path = self.project_path / output_file
        output_path.write_text(content, encoding='utf-8')
        print(f"📝 类方法映射已保存到: {output_path}")
        return output_path
    
    # 兼容性方法
    def save_enhanced_map(self, output_file: str = "enhanced_project_map.md") -> Path:
        """兼容性方法：保存增强版映射（基础版不支持）"""
        raise AttributeError("基础版类方法映射器不支持增强版映射")
    
    def get_language_summary(self) -> str:
        """兼容性方法：获取语言摘要（基础版不支持）"""
        raise AttributeError("基础版类方法映射器不支持语言摘要")
    
    def update_analysis(self, changed_files: Optional[List[Path]] = None) -> bool:
        """兼容性方法：更新分析（基础版不支持）"""
        raise AttributeError("基础版类方法映射器不支持update_analysis方法")
    
    def update_class_method_map(self, changed_files: Optional[List[Path]] = None) -> bool:
        """
        更新类方法映射
        Args:
            changed_files: 发生变化的文件列表，如果为None则重新分析整个项目
        Returns:
            是否成功更新
        """
        if changed_files is None:
            # 重新分析整个项目
            self.analyze_project()
        else:
            # 只更新变化的文件
            for file_path in changed_files:
                try:
                    # 从映射中移除该文件的旧记录
                    self._remove_file_from_maps(file_path)
                    # 重新分析该文件
                    self._analyze_file(file_path)
                except Exception as e:
                    print(f"⚠️  更新文件 {file_path} 时出错: {e}")
        
        # 保存更新后的映射
        self.save_class_method_map()
        return True
    
    def _remove_file_from_maps(self, file_path: Path):
        """从映射中移除文件记录"""
        relative_path = str(file_path.relative_to(self.project_path))
        
        # 从class_map中移除
        keys_to_remove = []
        for key in self.class_map.keys():
            if key.startswith(f"{relative_path}:"):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self.class_map[key]
        
        # 从function_map中移除
        keys_to_remove = []
        for key in self.function_map.keys():
            if key.startswith(f"{relative_path}:"):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self.function_map[key]
        
        # 从imports_map中移除
        if relative_path in self.imports_map:
            del self.imports_map[relative_path]
        
        # 从file_structure中移除
        if relative_path in self.file_structure:
            del self.file_structure[relative_path]


def analyze_and_generate_map(project_path: str) -> Path:
    """分析项目并生成类方法映射的便捷函数"""
    mapper = ClassMethodMapper(Path(project_path))
    mapper.analyze_project()
    return mapper.save_class_method_map()


# ============================================================================
# 增强功能：多语言项目分析
# ============================================================================

class MultiLangAnalyzer:
    """多语言代码分析器（从multi_lang_analyzer.py合并而来）"""
    
    # 语言文件扩展名映射
    LANGUAGE_EXTENSIONS = {
        'python': ['.py'],
        'javascript': ['.js', '.jsx'],
        'typescript': ['.ts', '.tsx'],
        'java': ['.java'],
        'go': ['.go'],
        'rust': ['.rs'],
        'c': ['.c', '.h'],
        'cpp': ['.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx'],
        'csharp': ['.cs'],
        'ruby': ['.rb'],
        'php': ['.php'],
        'swift': ['.swift'],
        'kotlin': ['.kt', '.kts'],
        'scala': ['.scala'],
        'html': ['.html', '.htm'],
        'css': ['.css'],
        'sql': ['.sql'],
        'shell': ['.sh', '.bash'],
        'yaml': ['.yaml', '.yml'],
        'json': ['.json'],
        'markdown': ['.md', '.markdown'],
        'text': ['.txt'],
    }
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.language_stats: Dict[str, Dict] = {}
        self.file_structure: Dict[str, Dict] = {}
        self.code_entities: Dict[str, List] = {}
        
    def analyze_project(self) -> Dict[str, Any]:
        """分析整个项目"""
        print(f"🔍 开始分析多语言项目结构: {self.project_path}")
        
        # 清空之前的分析结果
        self.language_stats.clear()
        self.file_structure.clear()
        self.code_entities.clear()
        
        # 初始化语言统计
        for lang in self.LANGUAGE_EXTENSIONS.keys():
            self.language_stats[lang] = {
                'file_count': 0,
                'total_lines': 0,
                'code_lines': 0,
                'comment_lines': 0,
                'blank_lines': 0,
            }
        
        # 分析所有文件
        total_files = 0
        analyzed_files = 0
        
        for file_path in self.project_path.rglob("*"):
            if file_path.is_file():
                total_files += 1
                # 跳过虚拟环境目录和缓存目录
                if any(skip in str(file_path) for skip in ['.venv', '__pycache__', '.git', '.aacode', 'node_modules', 'target', 'build', 'dist']):
                    continue
                    
                try:
                    lang = self._detect_language(file_path)
                    if lang:
                        self._analyze_file(file_path, lang)
                        analyzed_files += 1
                except Exception as e:
                    print(f"⚠️  分析文件 {file_path.relative_to(self.project_path)} 时出错: {e}")
        
        print(f"📁 找到 {total_files} 个文件，成功分析 {analyzed_files} 个代码文件")
        return self._generate_summary()
    
    def _detect_language(self, file_path: Path) -> Optional[str]:
        """检测文件语言"""
        ext = file_path.suffix.lower()
        
        for lang, extensions in self.LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return lang
        
        return None
    
    def _analyze_file(self, file_path: Path, lang: str):
        """分析单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            relative_path = str(file_path.relative_to(self.project_path))
            
            # 更新语言统计
            stats = self._count_file_stats(content)
            self.language_stats[lang]['file_count'] += 1
            self.language_stats[lang]['total_lines'] += stats['total_lines']
            self.language_stats[lang]['code_lines'] += stats['code_lines']
            self.language_stats[lang]['comment_lines'] += stats['comment_lines']
            self.language_stats[lang]['blank_lines'] += stats['blank_lines']
            
            # 解析代码结构
            entities = self._parse_file_content(content, lang, relative_path)
            
            # 存储文件结构
            self.file_structure[relative_path] = {
                'language': lang,
                'size': file_path.stat().st_size,
                'lines': stats['total_lines'],
                'entities': entities,
                'stats': stats,
            }
            
            # 存储代码实体
            if lang not in self.code_entities:
                self.code_entities[lang] = []
            self.code_entities[lang].extend(entities)
            
        except Exception as e:
            print(f"⚠️  分析文件 {file_path} 时出错: {e}")
    
    def _count_file_stats(self, content: str) -> Dict[str, int]:
        """统计文件行数"""
        lines = content.split('\n')
        total_lines = len(lines)
        
        code_lines = 0
        comment_lines = 0
        blank_lines = 0
        
        in_block_comment = False
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                blank_lines += 1
            elif stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('--'):
                comment_lines += 1
            elif stripped.startswith('/*'):
                comment_lines += 1
                if '*/' not in stripped:
                    in_block_comment = True
            elif '*/' in stripped:
                comment_lines += 1
                in_block_comment = False
            elif in_block_comment:
                comment_lines += 1
            else:
                code_lines += 1
        
        return {
            'total_lines': total_lines,
            'code_lines': code_lines,
            'comment_lines': comment_lines,
            'blank_lines': blank_lines,
        }
    
    def _parse_file_content(self, content: str, lang: str, file_path: str) -> List[Dict]:
        """解析文件内容，提取代码实体"""
        entities = []
        
        if lang == 'python':
            entities = self._parse_python(content, file_path)
        elif lang in ['javascript', 'typescript']:
            entities = self._parse_javascript(content, file_path, lang)
        elif lang == 'java':
            entities = self._parse_java(content, file_path)
        elif lang == 'go':
            entities = self._parse_go(content, file_path)
        elif lang == 'rust':
            entities = self._parse_rust(content, file_path)
        else:
            # 对于不支持详细解析的语言，至少提取函数和类的基本信息
            entities = self._parse_generic(content, file_path, lang)
        
        return entities
    
    def _parse_python(self, content: str, file_path: str) -> List[Dict]:
        """解析Python代码"""
        entities = []
        lines = content.split('\n')
        
        # 简单的Python解析
        class_pattern = re.compile(r'^class\s+(\w+)')
        function_pattern = re.compile(r'^def\s+(\w+)')
        async_function_pattern = re.compile(r'^async\s+def\s+(\w+)')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 检查类定义
            class_match = class_pattern.match(line_stripped)
            if class_match:
                entities.append({
                    'type': 'class',
                    'name': class_match.group(1),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'python',
                })
            
            # 检查函数定义
            func_match = function_pattern.match(line_stripped)
            async_func_match = async_function_pattern.match(line_stripped)
            
            if func_match:
                entities.append({
                    'type': 'function',
                    'name': func_match.group(1),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'python',
                    'async': False,
                })
            elif async_func_match:
                entities.append({
                    'type': 'function',
                    'name': async_func_match.group(1),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'python',
                    'async': True,
                })
        
        return entities
    
    def _parse_javascript(self, content: str, file_path: str, lang: str) -> List[Dict]:
        """解析JavaScript/TypeScript代码"""
        entities = []
        lines = content.split('\n')
        
        # JavaScript/TypeScript模式
        class_pattern = re.compile(r'^(export\s+)?(abstract\s+)?class\s+(\w+)')
        function_pattern = re.compile(r'^(export\s+)?(async\s+)?function\s+(\w+)')
        arrow_function_pattern = re.compile(r'^(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s*)?\([^)]*\)\s*=>')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 检查类定义
            class_match = class_pattern.match(line_stripped)
            if class_match:
                entities.append({
                    'type': 'class',
                    'name': class_match.group(3),
                    'line': i + 1,
                    'file': file_path,
                    'language': lang,
                    'exported': bool(class_match.group(1)),
                })
            
            # 检查函数定义
            func_match = function_pattern.match(line_stripped)
            if func_match:
                entities.append({
                    'type': 'function',
                    'name': func_match.group(3),
                    'line': i + 1,
                    'file': file_path,
                    'language': lang,
                    'async': bool(func_match.group(2)),
                    'exported': bool(func_match.group(1)),
                })
            
            # 检查箭头函数
            arrow_match = arrow_function_pattern.match(line_stripped)
            if arrow_match:
                entities.append({
                    'type': 'function',
                    'name': arrow_match.group(3),
                    'line': i + 1,
                    'file': file_path,
                    'language': lang,
                    'async': bool(arrow_match.group(4)),
                    'exported': bool(arrow_match.group(1)),
                    'arrow': True,
                })
        
        return entities
    
    def _parse_java(self, content: str, file_path: str) -> List[Dict]:
        """解析Java代码"""
        entities = []
        lines = content.split('\n')
        
        # Java模式
        class_pattern = re.compile(r'^(public|private|protected|static|final|abstract|sealed|non-sealed)?\s*(class|interface|enum|record)\s+(\w+)')
        method_pattern = re.compile(r'^(public|private|protected|static|final|abstract|synchronized|native|strictfp)?\s*(\w+\s+)*(\w+)\s*\([^)]*\)\s*{')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 检查类/接口/枚举定义
            class_match = class_pattern.match(line_stripped)
            if class_match:
                entities.append({
                    'type': class_match.group(2),  # class, interface, enum, record
                    'name': class_match.group(3),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'java',
                    'modifiers': class_match.group(1).split() if class_match.group(1) else [],
                })
            
            # 检查方法定义
            method_match = method_pattern.match(line_stripped)
            if method_match and 'class' not in line_stripped and 'interface' not in line_stripped:
                entities.append({
                    'type': 'method',
                    'name': method_match.group(3),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'java',
                    'modifiers': method_match.group(1).split() if method_match.group(1) else [],
                })
        
        return entities
    
    def _parse_go(self, content: str, file_path: str) -> List[Dict]:
        """解析Go代码"""
        entities = []
        lines = content.split('\n')
        
        # Go模式
        func_pattern = re.compile(r'^func\s+(\(\s*\*\s*\w+\s*\)\s*)?(\w+)\s*\([^)]*\)')
        struct_pattern = re.compile(r'^type\s+(\w+)\s+struct')
        interface_pattern = re.compile(r'^type\s+(\w+)\s+interface')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 检查函数定义
            func_match = func_pattern.match(line_stripped)
            if func_match:
                entities.append({
                    'type': 'function',
                    'name': func_match.group(2),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'go',
                    'receiver': func_match.group(1) if func_match.group(1) else None,
                })
            
            # 检查结构体定义
            struct_match = struct_pattern.match(line_stripped)
            if struct_match:
                entities.append({
                    'type': 'struct',
                    'name': struct_match.group(1),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'go',
                })
            
            # 检查接口定义
            interface_match = interface_pattern.match(line_stripped)
            if interface_match:
                entities.append({
                    'type': 'interface',
                    'name': interface_match.group(1),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'go',
                })
        
        return entities
    
    def _parse_rust(self, content: str, file_path: str) -> List[Dict]:
        """解析Rust代码"""
        entities = []
        lines = content.split('\n')
        
        # Rust模式
        struct_pattern = re.compile(r'^(pub\s+)?struct\s+(\w+)')
        enum_pattern = re.compile(r'^(pub\s+)?enum\s+(\w+)')
        trait_pattern = re.compile(r'^(pub\s+)?trait\s+(\w+)')
        function_pattern = re.compile(r'^(pub\s+)?fn\s+(\w+)\s*\([^)]*\)')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 检查结构体定义
            struct_match = struct_pattern.match(line_stripped)
            if struct_match:
                entities.append({
                    'type': 'struct',
                    'name': struct_match.group(2),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'rust',
                    'pub': bool(struct_match.group(1)),
                })
            
            # 检查枚举定义
            enum_match = enum_pattern.match(line_stripped)
            if enum_match:
                entities.append({
                    'type': 'enum',
                    'name': enum_match.group(2),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'rust',
                    'pub': bool(enum_match.group(1)),
                })
            
            # 检查trait定义
            trait_match = trait_pattern.match(line_stripped)
            if trait_match:
                entities.append({
                    'type': 'trait',
                    'name': trait_match.group(2),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'rust',
                    'pub': bool(trait_match.group(1)),
                })
            
            # 检查函数定义
            func_match = function_pattern.match(line_stripped)
            if func_match:
                entities.append({
                    'type': 'function',
                    'name': func_match.group(2),
                    'line': i + 1,
                    'file': file_path,
                    'language': 'rust',
                    'pub': bool(func_match.group(1)),
                })
        
        return entities
    
    def _parse_generic(self, content: str, file_path: str, lang: str) -> List[Dict]:
        """通用解析器，用于不支持详细解析的语言"""
        entities = []
        lines = content.split('\n')
        
        # 通用模式：查找看起来像函数或类定义的行
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 简单的启发式规则
            if lang in ['c', 'cpp', 'csharp']:
                # C家族语言：查找以类型开头的函数定义
                if re.match(r'^\w+\s+\w+\s*\([^)]*\)\s*{', line_stripped):
                    # 提取函数名
                    match = re.match(r'^\w+\s+(\w+)\s*\([^)]*\)', line_stripped)
                    if match:
                        entities.append({
                            'type': 'function',
                            'name': match.group(1),
                            'line': i + 1,
                            'file': file_path,
                            'language': lang,
                        })
            
            elif lang == 'ruby':
                # Ruby：查找def开头的行
                if line_stripped.startswith('def '):
                    name = line_stripped[4:].split('(')[0].strip()
                    entities.append({
                        'type': 'method',
                        'name': name,
                        'line': i + 1,
                        'file': file_path,
                        'language': lang,
                    })
            
            elif lang == 'php':
                # PHP：查找function开头的行
                if line_stripped.startswith('function '):
                    name = line_stripped[9:].split('(')[0].strip()
                    entities.append({
                        'type': 'function',
                        'name': name,
                        'line': i + 1,
                        'file': file_path,
                        'language': lang,
                    })
        
        return entities
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成分析摘要"""
        # 过滤有文件的语言
        active_languages = {lang: stats for lang, stats in self.language_stats.items() if stats['file_count'] > 0}
        
        # 计算总体统计
        total_files = sum(stats['file_count'] for stats in active_languages.values())
        total_lines = sum(stats['total_lines'] for stats in active_languages.values())
        
        return {
            'project_path': str(self.project_path),
            'total_files': total_files,
            'total_lines': total_lines,
            'languages': active_languages,
            'file_count': len(self.file_structure),
            'entity_count': sum(len(entities) for entities in self.code_entities.values()),
        }
    
    def generate_project_map(self) -> str:
        """生成项目映射的Markdown文档"""
        lines = []
        
        lines.append("# 多语言项目结构映射")
        lines.append("")
        lines.append(f"项目路径: `{self.project_path}`")
        lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"文件总数: {len(self.file_structure)}")
        lines.append(f"代码实体总数: {sum(len(entities) for entities in self.code_entities.values())}")
        lines.append("")
        
        # 语言统计
        lines.append("## 语言统计")
        lines.append("")
        lines.append("| 语言 | 文件数 | 总行数 | 代码行 | 注释行 | 空行 |")
        lines.append("|------|--------|--------|--------|--------|------|")
        
        for lang, stats in sorted(self.language_stats.items()):
            if stats['file_count'] > 0:
                lines.append(f"| {lang} | {stats['file_count']} | {stats['total_lines']} | {stats['code_lines']} | {stats['comment_lines']} | {stats['blank_lines']} |")
        
        lines.append("")
        
        # 按语言显示代码实体
        for lang, entities in sorted(self.code_entities.items()):
            if entities:
                lines.append(f"## {lang.capitalize()} 代码实体")
                lines.append("")
                
                # 按文件分组
                files = {}
                for entity in entities:
                    file_path = entity['file']
                    if file_path not in files:
                        files[file_path] = []
                    files[file_path].append(entity)
                
                for file_path, file_entities in sorted(files.items()):
                    lines.append(f"### 文件: `{file_path}`")
                    lines.append("")
                    
                    for entity in sorted(file_entities, key=lambda x: x['line']):
                        entity_type = entity.get('type', 'unknown')
                        entity_name = entity.get('name', 'unknown')
                        line_num = entity.get('line', 0)
                        
                        lines.append(f"- **第 {line_num} 行**: `{entity_type}` `{entity_name}`")
                        
                        # 添加额外信息
                        extra_info = []
                        if entity.get('async'):
                            extra_info.append('async')
                        if entity.get('exported'):
                            extra_info.append('exported')
                        if entity.get('pub'):
                            extra_info.append('pub')
                        if entity.get('modifiers'):
                            extra_info.extend(entity['modifiers'])
                        
                        if extra_info:
                            lines.append(f"  - 修饰符: {', '.join(extra_info)}")
                
                lines.append("")
        
        # 文件结构概览
        lines.append("## 文件结构概览")
        lines.append("")
        
        for file_path, file_info in sorted(self.file_structure.items()):
            lang = file_info['language']
            size_kb = file_info['size'] / 1024
            lines_count = file_info['lines']
            entity_count = len(file_info['entities'])
            
            lines.append(f"- `{file_path}`")
            lines.append(f"  - 语言: {lang}")
            lines.append(f"  - 大小: {size_kb:.1f} KB")
            lines.append(f"  - 行数: {lines_count}")
            lines.append(f"  - 实体数: {entity_count}")
            
            # 显示主要实体
            if entity_count > 0:
                main_entities = file_info['entities'][:3]  # 只显示前3个
                entity_names = [f"`{e['name']}`" for e in main_entities]
                lines.append(f"  - 主要实体: {', '.join(entity_names)}")
                if entity_count > 3:
                    lines.append(f"  - ... 还有 {entity_count - 3} 个实体")
        
        return '\n'.join(lines)
    
    def save_project_map(self, output_file: str = "project_structure_map.md") -> Path:
        """保存项目映射到文件"""
        content = self.generate_project_map()
        output_path = self.project_path / output_file
        output_path.write_text(content, encoding='utf-8')
        print(f"📝 项目结构映射已保存到: {output_path}")
        return output_path


# ============================================================================
# 增强版类方法映射器（保持向后兼容）
# ============================================================================

class EnhancedClassMethodMapper:
    """增强版类方法映射器（兼容旧接口）"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.python_mapper = ClassMethodMapper(project_path)
        self.multi_lang_analyzer = MultiLangAnalyzer(project_path)
        
    def analyze_project(self) -> Dict[str, Any]:
        """分析整个项目（多语言）"""
        print(f"🔍 开始增强版项目结构分析: {self.project_path}")
        
        # 分析Python代码（详细分析）
        python_summary = self.python_mapper.analyze_project()
        
        # 分析多语言代码（基础分析）
        multi_lang_summary = self.multi_lang_analyzer.analyze_project()
        
        # 合并结果
        combined_summary = {
            'project_path': str(self.project_path),
            'python_analysis': python_summary,
            'multi_lang_analysis': multi_lang_summary,
            'total_files': multi_lang_summary['total_files'],
            'total_lines': multi_lang_summary['total_lines'],
            'language_count': len(multi_lang_summary['languages']),
        }
        
        return combined_summary
    
    def generate_enhanced_map(self) -> str:
        """生成增强版项目映射"""
        # 获取Python详细映射
        python_map = self.python_mapper.generate_class_method_map()
        
        # 获取多语言映射
        multi_lang_map = self.multi_lang_analyzer.generate_project_map()
        
        # 合并映射
        lines = []
        lines.append("# 项目结构映射")
        lines.append("")
        lines.append("> 本文档包含项目的类、方法、函数等代码结构信息")
        lines.append("")
        lines.append(f"项目路径: `{self.project_path}`")
        lines.append("")
        
        # 添加多语言概览
        lines.append("## 多语言项目概览")
        lines.append("")
        lines.append(multi_lang_map.split("## 语言统计")[1].split("##")[0].strip())
        lines.append("")
        
        # 添加Python详细分析
        lines.append("## Python代码详细分析")
        lines.append("")
        # 跳过Python映射的标题部分
        python_content = python_map.split("# 项目类方法映射")[1]
        lines.append(python_content)
        
        return '\n'.join(lines)
    
    def save_enhanced_map(self, output_file: str = "project_structure.md") -> Path:
        """保存增强版映射到文件（项目结构：类、方法、函数等）"""
        content = self.generate_enhanced_map()
        output_path = self.project_path / output_file
        output_path.write_text(content, encoding='utf-8')
        print(f"📝 项目结构映射已保存到: {output_path}")
        return output_path
    
    def get_language_summary(self) -> str:
        """获取语言摘要（用于Agent提示）"""
        multi_lang_summary = self.multi_lang_analyzer._generate_summary()
        
        lines = []
        lines.append("## 项目语言构成")
        lines.append("")
        
        if not multi_lang_summary['languages']:
            lines.append("项目目录为空或没有可分析的代码文件。")
            return '\n'.join(lines)
        
        lines.append("检测到的编程语言:")
        for lang, stats in multi_lang_summary['languages'].items():
            lines.append(f"- **{lang}**: {stats['file_count']} 个文件, {stats['total_lines']} 行代码")
        
        lines.append("")
        lines.append("## 主要代码实体")
        lines.append("")
        
        # 显示主要语言的代码实体
        for lang, entities in self.multi_lang_analyzer.code_entities.items():
            if entities:
                entity_count = len(entities)
                # 按类型分组
                type_counts = {}
                for entity in entities:
                    entity_type = entity.get('type', 'unknown')
                    type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
                
                lines.append(f"**{lang.capitalize()}**: {entity_count} 个代码实体")
                for entity_type, count in type_counts.items():
                    lines.append(f"  - {entity_type}: {count} 个")
        
        return '\n'.join(lines)
    
    def update_analysis(self, changed_files: Optional[List[Path]] = None) -> bool:
        """更新分析结果"""
        try:
            # 更新Python分析
            self.python_mapper.update_class_method_map(changed_files)
            
            # 对于多语言分析，暂时重新分析整个项目
            # 未来可以优化为增量更新
            self.multi_lang_analyzer.analyze_project()
            
            return True
        except Exception as e:
            print(f"⚠️  更新分析失败: {e}")
            return False
    
    # 兼容性方法
    def update_class_method_map(self, changed_files: Optional[List[Path]] = None) -> bool:
        """兼容性方法：更新类方法映射（调用update_analysis）"""
        return self.update_analysis(changed_files)
    
    def save_class_method_map(self, output_file: str = "class_method_map.md") -> Path:
        """兼容性方法：保存类方法映射（调用基础版）"""
        return self.python_mapper.save_class_method_map(output_file)


def analyze_enhanced_project(project_path: str) -> Path:
    """分析增强版项目并生成映射的便捷函数"""
    mapper = EnhancedClassMethodMapper(Path(project_path))
    mapper.analyze_project()
    return mapper.save_enhanced_map()


if __name__ == "__main__":
    # 测试代码
    import sys
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        project_path = "."
    
    # 测试基本功能
    mapper = ClassMethodMapper(Path(project_path))
    mapper.analyze_project()
    output_file = mapper.save_class_method_map()
    print(f"✅ 基本分析完成，结果保存到: {output_file}")
    
    # 测试增强功能
    enhanced_mapper = EnhancedClassMethodMapper(Path(project_path))
    enhanced_mapper.analyze_project()
    enhanced_output = enhanced_mapper.save_enhanced_map()
    print(f"✅ 增强分析完成，结果保存到: {enhanced_output}")
    
    # 显示语言摘要
    summary = enhanced_mapper.get_language_summary()
    print(f"\n📊 语言摘要:")
    print(summary)