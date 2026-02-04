# 本地模拟模型
# utils/mock_model.py
"""
模拟本地模型，用于测试
"""
import asyncio
import json
import random
from typing import List, Dict, Any


class MockModel:
    """模拟模型类"""
    
    def __init__(self):
        self.responses = {
            "default": [
                "我需要分析这个任务并制定计划。\n\nAction: list_files\nAction Input: {\"pattern\": \"*\"}",
                "让我先查看项目结构，然后创建相应的文件。\n\nAction: write_file\nAction Input: {\"path\": \"hello.py\", \"content\": \"print('Hello, World!')\"}",
                "任务已完成。\n\n",
                "我需要运行这个程序来验证。\n\nAction: run_shell\nAction Input: {\"command\": \"python3 hello.py\"}",
                "程序运行成功，任务完成。\n\n"
            ],
            "create_file": [
                "我将创建一个hello world程序。\n\nAction: write_file\nAction Input: {\"path\": \"hello.py\", \"content\": \"#!/usr/bin/env python3\\nprint('Hello, World!')\"}"
            ],
            "run_file": [
                "让我运行这个程序。\n\nAction: run_shell\nAction Input: {\"command\": \"python3 hello.py\"}"
            ]
        }
    
    async def chat_completions_create(self, model: str, messages: List[Dict], 
                                     temperature: float = 0.1, max_tokens: int = 2000):
        """模拟聊天完成"""
        
        # 获取最后一条用户消息
        last_message = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_message = msg.get('content', '')
                break
        
        # 根据消息内容选择响应
        if "创建" in last_message or "create" in last_message.lower():
            response_text = random.choice(self.responses["create_file"])
        elif "运行" in last_message or "run" in last_message.lower():
            response_text = random.choice(self.responses["run_file"])
        else:
            response_text = random.choice(self.responses["default"])
        
        # 返回模拟响应
        class MockResponse:
            def __init__(self, content):
                self.choices = [MockChoice(content)]
        
        class MockChoice:
            def __init__(self, content):
                self.message = MockMessage(content)
        
        class MockMessage:
            def __init__(self, content):
                self.content = content
        
        return MockResponse(response_text)


async def create_mock_model_caller(model_config: Dict):
    """创建模拟模型调用器"""
    mock_model = MockModel()
    
    async def model_caller(messages: List[Dict]) -> str:
        try:
            # 如果有真实的API配置，尝试使用
            if model_config.get('api_key') and model_config.get('base_url'):
                try:
                    import openai
                    client = openai.OpenAI(
                        api_key=model_config.get('api_key'),
                        base_url=model_config.get('base_url')
                    )
                    
                    response = client.chat.completions.create(
                        model=model_config.get('name', 'gpt-4'),
                        messages=messages,
                        temperature=model_config.get('temperature', 0.1),
                        max_tokens=model_config.get('max_tokens', 2000)
                    )
                    
                    content = response.choices[0].message.content
                    return content if content is not None else ""
                except Exception as e:
                    print(f"🔄 真实模型调用失败，使用模拟模型: {e}")
            
            # 使用模拟模型
            response = await mock_model.chat_completions_create(
                model=model_config.get('name', 'mock'),
                messages=messages,
                temperature=model_config.get('temperature', 0.1),
                max_tokens=model_config.get('max_tokens', 2000)
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"模型调用失败: {str(e)}"
    
    return model_caller


if __name__ == "__main__":
    # 测试模拟模型
    async def test():
        caller = await create_mock_model_caller({})
        messages = [
            {"role": "system", "content": "你是一个AI助手"},
            {"role": "user", "content": "创建一个hello world程序"}
        ]
        response = await caller(messages)
        print(f"响应: {response}")
    
    asyncio.run(test())