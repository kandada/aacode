"""
API客户端技能实现
"""
import aiohttp
import json
import ssl
from typing import Dict, Any, Optional
from urllib.parse import urlencode


async def call_api(method: str,
                   url: str,
                   headers: Optional[Dict[str, str]] = None,
                   data: Optional[Dict] = None,
                   params: Optional[Dict] = None,
                   timeout: int = 30,
                   retry_count: int = 3) -> Dict[str, Any]:
    """
    发送HTTP请求

    Args:
        method: HTTP方法
        url: 请求URL
        headers: 请求头
        data: 请求数据（dict会自动转为JSON）
        params: URL参数
        timeout: 超时时间
        retry_count: 重试次数

    Returns:
        响应结果
    """
    default_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if headers:
        default_headers.update(headers)

    last_error = None
    for attempt in range(retry_count):
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            # 创建SSL上下文，禁用证书验证（仅用于测试）
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(
                timeout=timeout_obj,
                connector=connector
            ) as session:
                if params:
                    url = f"{url}?{urlencode(params)}"

                request_kwargs = {
                    "headers": default_headers
                }

                if data is not None:
                    if isinstance(data, dict):
                        request_kwargs["json"] = data
                    else:
                        request_kwargs["data"] = str(data)

                if method.upper() == "GET":
                    async with session.get(url, **request_kwargs) as response:
                        return await _format_response(response)
                elif method.upper() == "POST":
                    async with session.post(url, **request_kwargs) as response:
                        return await _format_response(response)
                elif method.upper() == "PUT":
                    async with session.put(url, **request_kwargs) as response:
                        return await _format_response(response)
                elif method.upper() == "DELETE":
                    async with session.delete(url, **request_kwargs) as response:
                        return await _format_response(response)
                else:
                    return {"success": False, "error": f"不支持的HTTP方法: {method}"}

        except aiohttp.ClientError as e:
            last_error = str(e)
            if attempt < retry_count - 1:
                continue

        except Exception as e:
            last_error = str(e)
            if attempt < retry_count - 1:
                continue

    return {"success": False, "error": f"请求失败: {last_error}"}


async def _format_response(response: aiohttp.ClientResponse) -> Dict[str, Any]:
    """格式化响应"""
    try:
        body = await response.text()
        try:
            body = json.loads(body)
        except:
            pass

        response_headers = {}
        for key, value in response.headers.items():
            response_headers[key] = value

        return {
            "success": response.status < 400,
            "status_code": response.status,
            "status_text": response.reason,
            "headers": response_headers,
            "body": body,
            "url": str(response.url)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"解析响应失败: {str(e)}"
        }
