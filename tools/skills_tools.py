"""
Skills工具层 - Skills加载和执行
tools/skills_tools.py
"""

import asyncio
import importlib.util
import inspect
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from utils.tool_registry import ToolRegistry, ToolSchema, ToolParameter


@dataclass
class SkillInfo:
    """Skill信息"""

    name: str
    description: str
    module_path: str
    function_name: str
    parameters: Dict[str, Any]
    examples: List[Dict[str, Any]]
    skill_dir: str
    # 新增：元数据字段，用于渐进式披露
    display_name: str = ""
    trigger_keywords: List[str] = field(default_factory=list)
    # 新增：加载状态标记
    metadata_loaded: bool = False
    full_instruction_loaded: bool = False


class SkillsManager:
    """Skills管理器"""

    def __init__(
        self, project_path: Path, skills_config: Optional[Dict[str, Any]] = None
    ):
        self.project_path = project_path
        # skills目录相对于项目根目录，而不是当前工作目录
        # 首先尝试从配置获取，默认为项目根目录下的skills
        skills_dir_name = "skills"
        if skills_config and "skills_dir" in skills_config:
            skills_dir_name = skills_config["skills_dir"]
        
        # 如果skills_dir是相对路径，假设相对于项目根目录
        skills_dir_path = Path(skills_dir_name)
        if not skills_dir_path.is_absolute():
            # 获取项目根目录（aacode_local目录）
            project_root = Path(__file__).parent.parent.absolute()
            self.skills_dir = project_root / skills_dir_name
        else:
            self.skills_dir = skills_dir_path
            
        self.loaded_skills: Dict[str, SkillInfo] = {}
        self.enabled_skills: List[str] = []
        # 新增：从配置加载的元数据
        self.skills_metadata: Dict[str, Dict[str, Any]] = {}
        if skills_config:
            self.skills_metadata = skills_config.get("skills_metadata", {})
            # 从配置加载启用的skills
            self.enabled_skills = skills_config.get("enabled_skills", [])

    def discover_skills(
        self, load_full_instructions: bool = False
    ) -> Dict[str, SkillInfo]:
        """发现并加载所有skills

        Args:
            load_full_instructions: 是否加载完整指令（默认只加载元数据）
        """
        if not self.skills_dir.exists():
            return {}

        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_name = skill_dir.name

                # 先检查是否有配置的元数据
                if skill_name in self.skills_metadata:
                    metadata = self.skills_metadata[skill_name]
                    # 创建基础SkillInfo（只包含元数据）
                    skill_info = SkillInfo(
                        name=skill_name,
                        description=metadata.get("description", ""),
                        module_path="",
                        function_name="",
                        parameters={},
                        examples=[],
                        skill_dir=str(skill_dir),
                        display_name=metadata.get("name", skill_name),
                        trigger_keywords=metadata.get("trigger_keywords", []),
                        metadata_loaded=True,
                        full_instruction_loaded=False,
                    )
                    self.loaded_skills[skill_name] = skill_info

                    # 如果需要加载完整指令
                    if load_full_instructions:
                        self._load_full_instruction(skill_name)
                else:
                    # 回退到原来的完整加载（兼容性）
                    skill_info = self._load_skill(skill_dir)
                    if skill_info:
                        self.loaded_skills[skill_info.name] = skill_info

        return self.loaded_skills

    def _load_full_instruction(self, skill_name: str) -> bool:
        """加载技能的完整指令（按需加载）"""
        if skill_name not in self.loaded_skills:
            return False

        skill_info = self.loaded_skills[skill_name]
        if skill_info.full_instruction_loaded:
            return True

        skill_dir = Path(skill_info.skill_dir)
        if not skill_dir.exists():
            return False

        # 加载完整技能信息
        full_info = self._load_skill(skill_dir)
        if full_info:
            # 合并信息，保留元数据
            skill_info.description = full_info.description
            skill_info.module_path = full_info.module_path
            skill_info.function_name = full_info.function_name
            skill_info.parameters = full_info.parameters
            skill_info.examples = full_info.examples
            skill_info.full_instruction_loaded = True
            return True

        return False

    def _load_skill(self, skill_dir: Path) -> Optional[SkillInfo]:
        """加载单个skill"""
        skill_name = skill_dir.name

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None

        description = self._read_skill_description(skill_md)

        impl_files = [
            f
            for f in skill_dir.iterdir()
            if f.is_file() and f.suffix == ".py" and f.name != "__pycache__"
        ]

        if not impl_files:
            return None

        main_impl = impl_files[0]
        func_name = self._find_main_function(main_impl)
        if not func_name:
            return None

        params, examples = self._extract_function_info(main_impl, func_name)

        return SkillInfo(
            name=skill_name,
            description=description,
            module_path=str(main_impl),
            function_name=func_name,
            parameters=params,
            examples=examples,
            skill_dir=str(skill_dir),
        )

    def _read_skill_description(self, skill_md: Path) -> str:
        """读取skill描述"""
        try:
            content = skill_md.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            description = lines[0] if lines else ""
            return description
        except:
            return ""

    def _find_main_function(self, impl_file: Path) -> Optional[str]:
        """查找主函数（完全自由命名，无前缀限制）"""
        try:
            # 读取源代码文件
            source = impl_file.read_text(encoding='utf-8')
            
            # 使用正则表达式查找函数定义，保持顺序
            import re
            
            # 查找所有函数定义
            function_pattern = r'^(async\s+)?def\s+(\w+)\s*\('
            lines = source.split('\n')
            
            functions = []
            for i, line in enumerate(lines):
                line = line.strip()
                match = re.match(function_pattern, line)
                if match:
                    is_async = bool(match.group(1))
                    func_name = match.group(2)
                    functions.append((func_name, is_async, i))
            
            if not functions:
                return None
            
            # 策略：优先选择第一个async函数
            async_funcs = [name for name, is_async, line_no in functions 
                          if is_async and not name.startswith('_')]
            if async_funcs:
                return async_funcs[0]
            
            # 如果没有async函数，选择第一个公共函数
            public_funcs = [name for name, is_async, line_no in functions 
                           if not name.startswith('_') and name != 'main']
            if public_funcs:
                return public_funcs[0]
            
            # 最后选择第一个函数
            return functions[0][0]
            
        except:
            # 回退方案：使用模块加载
            try:
                spec = importlib.util.spec_from_file_location("skill", impl_file)
                if spec is None or spec.loader is None:
                    return None

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 获取所有函数
                all_funcs = inspect.getmembers(module, inspect.isfunction)
                
                # 查找async函数
                async_funcs = []
                for name, func in all_funcs:
                    if asyncio.iscoroutinefunction(func) and not name.startswith('_'):
                        async_funcs.append(name)
                
                if async_funcs:
                    return async_funcs[0]
                
                # 查找公共函数
                public_funcs = []
                for name, func in all_funcs:
                    if not name.startswith('_') and name != 'main':
                        public_funcs.append(name)
                
                if public_funcs:
                    return public_funcs[0]
                
                return None
            except:
                return None

    def _extract_function_info(self, impl_file: Path, func_name: str) -> tuple:
        """提取函数参数和示例"""
        try:
            spec = importlib.util.spec_from_file_location("skill", impl_file)
            if spec is None or spec.loader is None:
                return {}, []

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            func = getattr(module, func_name, None)
            if not func:
                return {}, []

            sig = inspect.signature(func)
            params = {}
            for name, param in sig.parameters.items():
                if name in ("self", "kwargs"):
                    continue
                param_info = {
                    "type": (
                        param.annotation.__name__
                        if hasattr(param.annotation, "__name__")
                        else "Any"
                    ),
                    "required": param.default == inspect.Parameter.empty,
                    "description": "",
                }
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                params[name] = param_info

            examples = []
            docstring = func.__doc__ or ""
            return params, examples

        except:
            return {}, []

    async def execute_skill(self, skill_name: str, **kwargs) -> Dict[str, Any]:
        """执行skill"""
        if skill_name not in self.loaded_skills:
            return {"success": False, "error": f"Skill不存在: {skill_name}"}

        if skill_name not in self.enabled_skills:
            return {"success": False, "error": f"Skill未启用: {skill_name}"}

        skill_info = self.loaded_skills[skill_name]

        try:
            spec = importlib.util.spec_from_file_location(
                "skill", skill_info.module_path
            )
            if spec is None or spec.loader is None:
                return {
                    "success": False,
                    "error": f"无法加载skill模块: {skill_info.module_path}",
                }

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            func = getattr(module, skill_info.function_name)
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)

            if isinstance(result, dict) and "success" not in result:
                result = {"success": True, "result": result}

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def enable_skills(self, skill_names: List[str]):
        """启用skills"""
        for name in skill_names:
            if name in self.loaded_skills:
                self.enabled_skills.append(name)

    def list_enabled_skills(self) -> List[str]:
        """列出启用的skills"""
        return self.enabled_skills

    def get_skill_schema(self, skill_name: str) -> Optional[ToolSchema]:
        """获取skill的schema"""
        if skill_name not in self.loaded_skills:
            return None

        skill_info = self.loaded_skills[skill_name]

        params = []
        for name, info in skill_info.parameters.items():
            param = ToolParameter(
                name=name,
                type=str,
                required=info.get("required", False),
                default=info.get("default"),
                description=info.get("description", ""),
            )
            params.append(param)

        return ToolSchema(
            name=skill_name,
            description=skill_info.description,
            parameters=params,
            examples=skill_info.examples,
        )

    def get_all_skills_doc(self) -> str:
        """获取所有skills文档"""
        if not self.loaded_skills:
            return "# 可用Skills\n\n暂无可用的Skills"

        doc = "# 可用Skills\n\n"
        for name, skill in self.loaded_skills.items():
            status = "✅" if name in self.enabled_skills else "❌"
            doc += f"## {status} {name}\n\n"
            doc += f"{skill.description}\n\n"
            if skill.parameters:
                doc += "### 参数\n\n"
                for param_name, param_info in skill.parameters.items():
                    required = "必需" if param_info.get("required") else "可选"
                    doc += f"- `{param_name}` ({param_info.get('type', 'Any')}, {required})\n"
            doc += "\n---\n\n"

        return doc
