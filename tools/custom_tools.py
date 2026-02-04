# 可在此自定义工具
# tools/custom_tools.py
from tools.atomic_tools import AtomicTools
from typing import Optional, Dict, Any


class CustomTools(AtomicTools):
    """自定义工具扩展"""

    async def analyze_code(self, file_path: str) -> Dict[str, Any]:
        """代码分析工具"""
        # 读取文件
        result = await self.read_file(file_path)
        if not result.get("success"):
            return result

        code = result["content"]

        # 执行代码分析
        analysis_code = f"""
import ast
import json

code = '''{code}'''

def analyze_python_code(code_str):
    try:
        tree = ast.parse(code_str)

        analysis = {
        "functions": [],
            "classes": [],
            "imports": [],
            "complexity": 0
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                analysis["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                analysis["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    analysis["imports"].append(n.name)
            elif isinstance(node, ast.ImportFrom):
                analysis["imports"].append(f"{{node.module}}.*")

        return analysis
    except Exception as e:
        return {{"error": str(e)}}

result = analyze_python_code(code)
print(json.dumps(result, indent=2))
"""

        # 执行分析
        return await self.execute_python(analysis_code)


