# 多模态工具
# tools/multimodal_tools.py
"""
多模态理解工具 - 支持图片和视频理解
"""

import asyncio
import base64
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import openai
from config import settings


class MultimodalTools:
    """多模态理解工具集"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._init_model_config()

    def _init_model_config(self):
        """初始化多模态模型配置"""
        self.enabled = getattr(settings.multimodal, "enabled", True)
        self.default_model = getattr(
            settings.multimodal, "default_model", "moonshot_kimi_k2.5"
        )
        self.models = getattr(settings.multimodal, "models", {})

        # 获取当前默认模型的配置
        self.current_model_config = self.models.get(self.default_model, {})

        # 检查主模型是否支持多模态，如果支持则使用主模型
        self._check_main_model_multimodal()

    def _check_main_model_multimodal(self):
        """检查主模型是否支持多模态"""
        main_model_name = settings.model.name.lower()
        main_model_gateway = settings.model.gateway

        # 检查是否是多模态模型
        if "minimax" in main_model_name or "kimi" in main_model_name:
            print(f"🔍 检测到主模型 '{settings.model.name}' 支持多模态")

            # 如果主模型是多模态模型，优先使用主模型配置
            if "minimax" in main_model_name:
                model_key = "minimax_m2.5"
                if model_key in self.models:
                    self.default_model = model_key
                    self.current_model_config = self.models[model_key]
                    print(f"✅ 多模态工具将使用主模型: MiniMax-M2.5")
                else:
                    # 动态创建MiniMax配置
                    self._create_minimax_config()
            elif "kimi" in main_model_name:
                model_key = "moonshot_kimi_k2.5"
                if model_key in self.models:
                    self.default_model = model_key
                    self.current_model_config = self.models[model_key]
                    print(f"✅ 多模态工具将使用主模型: Kimi-K2.5")

    def _create_minimax_config(self):
        """动态创建MiniMax多模态配置"""
        minimax_config = {
            "name": "MiniMax-M2.5",
            "provider": "minimax",
            "gateway": "anthropic",
            "base_url": (
                settings.model.base_url
                or os.getenv("MULTIMODAL_API_URL")
                or "https://api.minimax.chat/v1"
            ),
            "api_key": settings.model.api_key or os.getenv("LLM_API_KEY"),
            "vision": True,
            "video": True,
            "max_image_size": 10485760,
            "max_video_size": 104857600,
            "supported_formats": {
                "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
                "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
            },
        }

        # 添加到模型配置
        self.models["minimax_m2.5"] = minimax_config
        self.default_model = "minimax_m2.5"
        self.current_model_config = minimax_config
        print(f"✅ 已创建MiniMax多模态配置")

    def _get_model_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """获取指定模型的配置"""
        if model_name is None:
            model_name = self.default_model
        return self.models.get(model_name, self.current_model_config)

    def _encode_image(self, image_path: str) -> str:
        """将图片编码为base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _validate_file(
        self, file_path: str, file_type: str = "image"
    ) -> Dict[str, Any]:
        """验证文件是否存在且格式正确"""
        model_config = self.current_model_config

        if file_type == "image":
            allowed_formats = model_config.get("supported_formats", {}).get(
                "images", [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
            )
            max_size = model_config.get("max_image_size", 10485760)
        else:
            allowed_formats = model_config.get("supported_formats", {}).get(
                "videos", [".mp4", ".avi", ".mov", ".mkv", ".webm"]
            )
            max_size = model_config.get("max_video_size", 104857600)

        # 检查文件是否存在
        if not os.path.exists(file_path):
            return {"valid": False, "error": f"文件不存在: {file_path}"}

        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            actual_size_mb = file_size / (1024 * 1024)
            return {
                "valid": False,
                "error": f"文件过大: {actual_size_mb:.1f}MB, 最大支持: {max_size_mb}MB",
            }

        # 检查文件格式
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in allowed_formats:
            return {
                "valid": False,
                "error": f"不支持的文件格式: {file_ext}, 支持的格式: {', '.join(allowed_formats)}",
            }

        return {"valid": True, "size": file_size}

    async def understand_image(
        self, image_path: str, prompt: str = "请详细描述这张图片的内容", **kwargs
    ) -> Dict[str, Any]:
        """
        理解单张或多张图片的内容

        Args:
            image_path: 图片路径，支持单张图片或用逗号分隔的多张图片路径
                       例如: "image1.jpg" 或 "image1.jpg,image2.png"
            prompt: 提问内容
            **kwargs: 其他参数（用于兼容）
        """
        try:
            model_config = self._get_model_config(kwargs.get("model"))

            # 处理多张图片
            image_paths = [p.strip() for p in image_path.split(",")]

            # 解析所有图片路径为完整路径
            resolved_paths: List[Path] = []
            for img_path in image_paths:
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)
                resolved_paths.append(full_path)

            # 验证所有图片
            for img_path in resolved_paths:
                validate_result = self._validate_file(str(img_path), "image")
                if not validate_result["valid"]:
                    return {"error": validate_result["error"]}

            # 编码所有图片
            image_contents = []
            for img_path in image_paths:
                # 如果是相对路径，尝试相对于项目路径
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)

                base64_image = self._encode_image(str(full_path))
                image_contents.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{Path(full_path).suffix[1:]};base64,{base64_image}"
                        },
                    }
                )

            # 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, *image_contents],
                }
            ]

            # 调用API
            response = await self._call_vision_api(messages, model_config)

            return {
                "success": True,
                "description": response,
                "images_count": len(image_paths),
                "images": image_paths,
            }

        except Exception as e:
            return {"error": f"图片理解失败: {str(e)}"}

    async def understand_video(
        self,
        video_path: str,
        prompt: str = "请详细描述这个视频的内容，包括场景、人物、动作等",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        理解视频内容

        Args:
            video_path: 视频文件路径
            prompt: 提问内容
            **kwargs: 其他参数
        """
        try:
            model_config = self._get_model_config(kwargs.get("model"))

            # 检查模型是否支持视频
            if not model_config.get("video", False):
                return {"error": f"当前模型 {model_config.get('name')} 不支持视频理解"}

            # 解析视频路径为完整路径
            video_full_path = Path(video_path)
            if not video_full_path.is_absolute():
                video_full_path = self.project_path / video_path

            # 验证视频文件
            validate_result = self._validate_file(str(video_full_path), "video")
            if not validate_result["valid"]:
                return {"error": validate_result["error"]}

            # 对于视频，需要将视频帧提取或使用其他方式处理
            # 这里使用 base64 编码视频（注意：视频过大会导致API调用失败）
            # Kimi K2.5 原生支持视频输入

            # 读取视频文件并编码
            with open(str(video_full_path), "rb") as video_file:
                base64_video = base64.b64encode(video_file.read()).decode("utf-8")

            # 构建消息 - 视频使用 url 类型
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": f"data:video/{video_full_path.suffix[1:]};base64,{base64_video}"
                            },
                        },
                    ],
                }
            ]

            # 调用API
            response = await self._call_vision_api(messages, model_config)

            return {
                "success": True,
                "description": response,
                "video": str(video_full_path),
            }

        except Exception as e:
            return {"error": f"视频理解失败: {str(e)}"}

    async def understand_ui_design(
        self,
        design_path: str,
        prompt: str = "请详细分析这个UI设计稿，描述布局、色彩、组件等，并尝试生成对应的HTML/CSS前端代码",
        generate_code: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        理解UI设计稿并生成前端代码

        Args:
            design_path: 设计稿路径（图片或多个图片）
            prompt: 提问内容
            generate_code: 是否生成前端代码
            **kwargs: 其他参数
        """
        try:
            model_config = self._get_model_config(kwargs.get("model"))

            # 处理多张图片
            design_paths = [p.strip() for p in design_path.split(",")]

            # 解析所有图片路径为完整路径
            resolved_paths: List[Path] = []
            for img_path in design_paths:
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)
                resolved_paths.append(full_path)

            # 验证所有图片
            for img_path in resolved_paths:
                validate_result = self._validate_file(str(img_path), "image")
                if not validate_result["valid"]:
                    return {"error": validate_result["error"]}

            # 构建更详细的prompt
            if generate_code:
                full_prompt = f"""{prompt}

请按照以下格式输出分析结果：

## UI分析
1. 整体布局：
2. 色彩方案：
3. 字体：
4. 组件：
5. 响应式设计：

## 前端代码
请生成对应的HTML/CSS代码（使用纯CSS，不依赖任何框架）：
```html
<!-- 完整代码 -->
```
"""
            else:
                full_prompt = prompt

            # 编码所有图片
            image_contents = []
            for img_path in design_paths:
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)

                base64_image = self._encode_image(str(full_path))
                image_contents.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{Path(full_path).suffix[1:]};base64,{base64_image}"
                        },
                    }
                )

            messages = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": full_prompt}, *image_contents],
                }
            ]

            # 调用API
            response = await self._call_vision_api(messages, model_config)

            return {
                "success": True,
                "analysis": response,
                "designs_count": len(design_paths),
                "designs": design_paths,
                "code_generated": generate_code,
            }

        except Exception as e:
            return {"error": f"UI设计稿理解失败: {str(e)}"}

    async def _call_vision_api(self, messages: List[Dict], model_config: Dict) -> str:
        """调用多模态模型的API"""
        api_key = (
            model_config.get("api_key")
            or os.getenv("MULTIMODAL_API_KEY")
            or settings.model.api_key
        )
        base_url = (
            model_config.get("base_url")
            or os.getenv("MULTIMODAL_API_URL")
            or "https://api.moonshot.cn/v1"
        )
        model_name = model_config.get("name") or "kimi-k2.5"

        if not api_key:
            raise ValueError("未设置多模态模型API密钥")

        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

        # 简化消息格式以兼容所有API
        simplified_messages = self._simplify_messages_for_api(messages)

        # 根据不同模型调整参数
        provider = model_config.get("provider", "moonshot")
        try:
            if provider == "moonshot":
                # Kimi 模型 - 使用类型转换避免类型检查问题
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=simplified_messages,  # type: ignore
                    max_tokens=4096,
                )
            else:
                # MiniMax 和其他模型
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=simplified_messages,  # type: ignore
                    temperature=0.7,
                    max_tokens=4096,
                )

            content = response.choices[0].message.content
            return content if content is not None else ""

        except Exception as e:
            error_msg = str(e)
            print(f"⚠️  多模态API调用失败: {error_msg}")
            print("💡 尝试使用文本模式...")

            # 回退到纯文本模式
            text_only_messages = self._convert_to_text_only(messages)
            response = client.chat.completions.create(
                model=model_name,
                messages=text_only_messages,  # type: ignore
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            return content if content is not None else ""

    def _simplify_messages_for_api(self, messages: List[Dict]) -> List[Dict[str, Any]]:
        """简化消息格式以兼容API"""
        simplified = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, list):
                # 处理多模态消息
                api_content = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            api_content.append(
                                {"type": "text", "text": part.get("text", "")}
                            )
                        elif part.get("type") == "image_url" and isinstance(
                            part.get("image_url"), dict
                        ):
                            api_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": part["image_url"].get("url", "")
                                    },
                                }
                            )
                simplified.append({"role": role, "content": api_content})
            else:
                simplified.append({"role": role, "content": content})
        return simplified

    def _convert_to_text_only(self, messages: List[Dict]) -> List[Dict[str, str]]:
        """将消息转换为纯文本格式"""
        text_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, list):
                # 提取所有文本部分
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                text_content = " ".join(text_parts) if text_parts else "[包含图片内容]"
                text_messages.append({"role": role, "content": text_content})
            else:
                text_messages.append({"role": role, "content": str(content)})
        return text_messages

    async def analyze_image_consistency(
        self,
        image_paths: str,
        prompt: str = "请分析这些图片中人物的相似度，判断是否为同一人",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        分析多张图片中的人物一致性

        Args:
            image_paths: 多张图片路径，用逗号分隔
            prompt: 提问内容
            **kwargs: 其他参数
        """
        try:
            model_config = self._get_model_config(kwargs.get("model"))

            # 处理多张图片
            paths = [p.strip() for p in image_paths.split(",")]

            if len(paths) < 2:
                return {"error": "需要至少两张图片进行一致性分析"}

            # 解析所有图片路径为完整路径
            resolved_paths: List[Path] = []
            for img_path in paths:
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)
                resolved_paths.append(full_path)

            # 验证所有图片
            for img_path in resolved_paths:
                validate_result = self._validate_file(str(img_path), "image")
                if not validate_result["valid"]:
                    return {"error": validate_result["error"]}

            # 编码所有图片
            image_contents = []
            for img_path in paths:
                if not os.path.isabs(img_path):
                    full_path = self.project_path / img_path
                else:
                    full_path = Path(img_path)

                base64_image = self._encode_image(str(full_path))
                image_contents.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{Path(full_path).suffix[1:]};base64,{base64_image}"
                        },
                    }
                )

            full_prompt = f"""{prompt}

请分析这些图片中的一致性：
1. 如果是人物图片，请判断面部特征、穿着、场景等是否一致
2. 如果是物体图片，请分析样式、颜色、特征等是否一致
3. 给出相似度评分（0-100%）和详细分析
"""

            messages = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": full_prompt}, *image_contents],
                }
            ]

            response = await self._call_vision_api(messages, model_config)

            return {
                "success": True,
                "analysis": response,
                "images_count": len(paths),
                "images": paths,
            }

        except Exception as e:
            return {"error": f"一致性分析失败: {str(e)}"}


def get_multimodal_tools_schema() -> List[Dict[str, Any]]:
    """获取多模态工具的schema定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "understand_image",
                "description": "理解图片内容 - 支持单张或多张图片的理解。可以用于分析截图、照片、设计稿等图片内容。这个工具特别适合需要查看图片但不需要生成代码的场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "图片路径，支持单张或多张（用逗号分隔）。例如：'screenshot.png' 或 'img1.jpg,img2.png'",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "你想要了解图片的什么问题？例如：'这张图片的主要内容是什么？'",
                        },
                    },
                    "required": ["image_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "understand_video",
                "description": "理解视频内容 - 分析视频中的场景、人物、动作等。需要视频文件路径。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "video_path": {"type": "string", "description": "视频文件路径"},
                        "prompt": {
                            "type": "string",
                            "description": "你想要了解视频的什么问题？例如：'视频中发生了什么？'",
                        },
                    },
                    "required": ["video_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "understand_ui_design",
                "description": "理解UI设计稿/页面截图并生成前端代码 - 这是进行前端开发时的重要工具。可以分析设计稿或页面截图，描述UI布局、色彩、组件等，并尝试生成对应的HTML/CSS代码。这个工具结合了多模态理解和前端开发知识，避免理解与代码脱节。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "design_path": {
                            "type": "string",
                            "description": "设计稿路径，支持单张或多张（用逗号分隔）。例如：'mockup.png' 或 'desktop.png,mobile.png'",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "你想要如何分析这个设计稿？例如：'请分析这个登录页面设计'",
                        },
                        "generate_code": {
                            "type": "boolean",
                            "description": "是否生成前端代码，默认为true",
                            "default": True,
                        },
                    },
                    "required": ["design_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_image_consistency",
                "description": "分析多张图片的一致性（人物或物体）- 用于检查多张图片中的人物是否为同一人，或者物体样式是否一致。适用于图片创作和视频制作场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_paths": {
                            "type": "string",
                            "description": "多张图片路径，用逗号分隔。例如：'person1.jpg,person2.jpg'",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "你想要分析哪些方面的一致性？",
                        },
                    },
                    "required": ["image_paths"],
                },
            },
        },
    ]
