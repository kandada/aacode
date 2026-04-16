# tools/web_tools.py
"""
网络搜索工具实现
只支持searXNG搜索引擎聚合器
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import quote, urljoin
import os
import time


class WebTools:
    """网络搜索和Web操作工具（只支持searXNG）"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self.session: Optional[aiohttp.ClientSession] = None
        self.search_engines = {
            "searxng": {
                "url": os.getenv("SEARCHXNG_URL", "http://localhost:8080").rstrip(
                    "/search"
                ),
                "enabled": bool(os.getenv("SEARCHXNG_URL")),
                "description": "自托管搜索引擎聚合器（集成Google、Bing、百度、搜狗等）",
            }
        }
        self.last_search_time: dict[str, float] = {}

    async def _ensure_session(self):
        """确保HTTP会话存在"""
        if self.session is None or self.session.closed:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            if __package__ in (None, ""):
                from config import settings
            else:
                from ..config import settings

            web_timeout = settings.timeouts.web_request
            timeout = aiohttp.ClientTimeout(total=web_timeout, connect=10)

            # 创建SSL上下文，允许自签名证书（用于本地searXNG实例）
            import ssl

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                force_close=False,
                enable_cleanup_closed=True,
                ssl=ssl_context,
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                },
            )
        # 确保session不为None
        assert self.session is not None, "Session should be initialized"

    async def search_web(
        self,
        query: str,
        engine: str = "auto",
        max_results: int = 10,
        safe_search: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        网络搜索（只支持searxng）

        Args:
            query: 搜索查询
            engine: 搜索引擎 (只支持searxng或auto)
            max_results: 最大结果数
            safe_search: 是否启用安全搜索

        注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
            搜索结果
        """
        try:
            await self._ensure_session()

            # 选择搜索引擎
            if engine == "auto":
                engine = self._choose_best_engine()

            if not self.search_engines.get(engine, {}).get("enabled", False):
                return {
                    "success": False,
                    "error": f"搜索引擎 {engine} 不可用",
                    "available_engines": [
                        k for k, v in self.search_engines.items() if v.get("enabled")
                    ],
                }

            # 速率限制检查
            if not self._check_rate_limit(engine):
                return {
                    "success": False,
                    "error": f"搜索引擎 {engine} 速率限制中,请稍后重试",
                }

            # 执行搜索
            results = await self._search_with_fallback(
                query, engine, max_results, safe_search
            )

            # 更新速率限制
            if results.get("success"):
                used_engine = results.get("engine", engine)
                self.last_search_time[used_engine] = time.time()

            return results

        except Exception as e:
            return {"success": False, "error": f"搜索失败: {str(e)}"}

    async def fetch_url(
        self,
        url: str,
        timeout: Optional[int] = None,
        max_content_length: int = 100000,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        获取网页内容

        Args:
            url: 网页URL
            timeout: 超时时间(秒),默认使用配置值
            max_content_length: 最大内容长度

         注意:**kwargs 用于接收并忽略模型可能传入的额外参数

        Returns:
             网页内容
        """
        try:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            if timeout is None:
                if __package__ in (None, ""):
                    from config import settings
                else:
                    from ..config import settings

                timeout = settings.timeouts.web_request

            await self._ensure_session()
            # 类型检查器需要知道session不为None
            session = self.session
            assert session is not None, "Session should be initialized"

            # URL安全检查
            if not self._is_safe_url(url):
                return {"success": False, "error": "URL安全检查失败"}

            if timeout is None:
                timeout = 30
            client_timeout = aiohttp.ClientTimeout(total=timeout)

            async with session.get(url, timeout=client_timeout) as response:
                content_type = response.headers.get("content-type", "").lower()

                # 只处理文本内容
                if not any(
                    ct in content_type
                    for ct in ["text/html", "text/plain", "application/json"]
                ):
                    return {
                        "success": False,
                        "error": f"不支持的内容类型: {content_type}",
                    }

                content = await response.text(errors="ignore")

                # 限制内容长度
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "\n...[内容已截断]"

                return {
                    "success": True,
                    "url": url,
                    "status_code": response.status,
                    "content_type": content_type,
                    "content_length": len(content),
                    "content": content,
                }

        except asyncio.TimeoutError:
            return {"success": False, "error": f"请求超时 ({timeout}秒)"}
        except Exception as e:
            return {"success": False, "error": f"获取网页失败: {str(e)}"}

    def _choose_best_engine(self) -> str:
        """选择最佳搜索引擎"""
        # 只支持searxng
        if self.search_engines.get("searxng", {}).get("enabled", False):
            return "searxng"

        # 如果没有可用的引擎，返回空字符串
        return ""

    async def _search_with_fallback(
        self, query: str, engine: str, max_results: int, safe_search: bool
    ) -> Dict[str, Any]:
        """搜索实现（只支持searxng）"""
        # 只支持searxng
        if engine == "auto":
            engine = "searxng"

        if engine != "searxng":
            return {
                "success": False,
                "error": f"不支持的搜索引擎: {engine}，当前只支持searxng",
                "query": query,
                "suggestion": "请配置SEARCHXNG_URL环境变量",
            }

        # 检查searxng是否启用
        if not self.search_engines.get("searxng", {}).get("enabled", False):
            return {
                "success": False,
                "error": "searxng搜索引擎未启用",
                "query": query,
                "suggestion": "请设置SEARCHXNG_URL环境变量指向您的searXNG实例",
            }

        try:
            print(f"🔍 使用搜索引擎: {engine}")
            result = await self._search_searxng(query, max_results, safe_search)
            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"searxng搜索失败: {str(e)}",
                "query": query,
                "suggestion": "请检查searXNG实例是否正常运行，网络连接是否正常",
            }

    def _check_rate_limit(self, engine: str) -> bool:
        """检查速率限制"""
        last_time = self.last_search_time.get(engine, 0)
        rate_limit_value = self.search_engines.get(engine, {}).get("rate_limit", 1.0)

        # 确保rate_limit是数值类型
        try:
            rate_limit = float(rate_limit_value)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            rate_limit = 1.0  # 默认值

        # 对于searxng，放宽速率限制，因为它是本地实例
        if engine == "searxng":
            rate_limit = 0.5  # 0.5秒

        return time.time() - last_time >= rate_limit

    def _is_safe_url(self, url: str) -> bool:
        """URL安全检查"""
        try:
            # 基本URL格式检查
            if not url.startswith(("http://", "https://")):
                return False

            # 检查是否为内网地址
            import ipaddress
            from urllib.parse import urlparse

            parsed = urlparse(url)
            hostname = parsed.hostname

            if not hostname:
                return False

            # 允许localhost和searxng本地实例
            if hostname in ["localhost", "127.0.0.1", "::1"]:
                return True

            # 检查是否为私有IP
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private:
                    return self.safety_guard.allow_local_network
            except ValueError:
                # 不是IP地址，是域名
                pass

            # 默认允许
            return True

        except Exception:
            return False

    async def _search_searxng(
        self, query: str, max_results: int, safe_search: bool
    ) -> Dict[str, Any]:
        """使用searXNG搜索"""
        try:
            base_url = self.search_engines["searxng"]["url"]
            search_url = f"{base_url}/search"

            # 根据searXNG文档使用正确的参数
            # https://docs.searxng.org/dev/search_api.html
            base_params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "auto",  # 自动检测语言
                "safesearch": 1 if safe_search else 0,
                "pageno": 1,  # 第一页
            }

            # 尝试不同的参数组合
            param_variations = [
                base_params,  # 原始参数
                {**base_params, "format": "html"},  # 尝试HTML格式
                {k: v for k, v in base_params.items() if k != "format"},  # 无format参数
                {**base_params, "engines": "google,duckduckgo,bing"},  # 指定引擎
            ]

            # 使用配置的超时时间
            if __package__ in (None, ""):
                from config import settings
            else:
                from ..config import settings

            web_timeout = settings.timeouts.web_request
            client_timeout = aiohttp.ClientTimeout(total=web_timeout)

            last_error = None
            for i, test_params in enumerate(param_variations):
                try:
                    print(f"🔍 尝试参数组合 {i + 1}: {test_params}")
                    # 确保session存在
                    if self.session is None:
                        await self._ensure_session()
                    # 类型检查器需要知道session不为None
                    session = self.session
                    assert session is not None, "Session should be initialized"
                    async with session.get(
                        search_url, params=test_params, timeout=client_timeout
                    ) as response:
                        if response.status == 200:
                            content_type = response.headers.get(
                                "content-type", ""
                            ).lower()

                            if "application/json" in content_type:
                                data = await response.json()

                                # 检查是否有错误
                                if data.get("error"):
                                    last_error = f"SearXNG错误: {data.get('error')}"
                                    continue

                                # 检查是否有结果
                                results = data.get("results", [])
                                if not results:
                                    last_error = "SearXNG返回空结果"
                                    continue

                                # 处理结果
                                processed_results = []
                                for item in results[:max_results]:
                                    processed_results.append(
                                        {
                                            "title": item.get("title", ""),
                                            "url": item.get("url", ""),
                                            "content": item.get("content", ""),
                                            "engine": item.get("engine", "searxng"),
                                            "score": item.get("score", 0),
                                        }
                                    )

                                return {
                                    "success": True,
                                    "engine": "searxng",
                                    "query": query,
                                    "results": processed_results,
                                    "total_results": len(processed_results),
                                }
                            else:
                                # 尝试解析HTML响应
                                html = await response.text()
                                # 简单提取结果（实际应该用BeautifulSoup等库）
                                import re

                                # 这里简化处理，实际应该更复杂
                                last_error = "SearXNG返回HTML格式，需要解析"
                                continue

                        else:
                            last_error = f"SearXNG HTTP错误: {response.status}"
                            continue

                except asyncio.TimeoutError:
                    last_error = f"参数组合 {i + 1} 超时"
                    continue
                except Exception as e:
                    last_error = f"参数组合 {i + 1} 错误: {str(e)}"
                    continue

            return {
                "success": False,
                "error": f"SearXNG搜索失败: {last_error}",
                "query": query,
                "suggestion": "请检查searXNG配置和网络连接",
            }

        except Exception as e:
            return {"success": False, "error": f"SearXNG搜索失败: {str(e)}"}

    async def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """兼容性方法"""
        result = await self.search_web(query, engine="searxng", max_results=max_results)

        # 转换为旧格式
        if result.get("success"):
            return {
                "success": True,
                "query": query,
                "results": result.get("results", []),
                "count": len(result.get("results", [])),
            }
        else:
            return {"error": result.get("error", "搜索失败"), "success": False}

    async def search_code(
        self, query: str, language: str = "", max_results: int = 10
    ) -> Dict[str, Any]:
        """
        搜索代码示例

        Args:
            query: 搜索查询
            language: 编程语言
            max_results: 最大结果数

        Returns:
            代码搜索结果
        """
        try:
            # 使用GitHub API搜索代码
            search_query = f"{query} language:{language}" if language else query
            url = f"https://api.github.com/search/code?q={quote(search_query)}&per_page={max_results}"

            await self._ensure_session()
            # 类型检查器需要知道session不为None
            session = self.session
            assert session is not None, "Session should be initialized"

            headers = {}
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"token {github_token}"

            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    results = []
                    for item in data.get("items", []):
                        results.append(
                            {
                                "repository": item["repository"]["full_name"],
                                "file": item["name"],
                                "path": item["path"],
                                "url": item["html_url"],
                                "description": item["repository"].get(
                                    "description", ""
                                ),
                                "stars": item["repository"].get("stargazers_count", 0),
                            }
                        )

                    return {
                        "success": True,
                        "query": query,
                        "language": language,
                        "results": results,
                        "total_count": data.get("total_count", 0),
                    }
                else:
                    return {
                        "success": False,
                        "error": f"GitHub API错误: {response.status}",
                    }

        except Exception as e:
            return {"success": False, "error": f"代码搜索失败: {str(e)}"}

    async def cleanup(self):
        """清理资源，关闭HTTP会话"""
        if hasattr(self, "session") and self.session and not self.session.closed:
            try:
                await self.session.close()
                # 等待底层 connector 释放连接，避免 Windows 上 _sock.fileno() 错误
                await asyncio.sleep(0.25)
            except Exception:
                pass
            self.session = None

    def __del__(self):
        """析构函数 - 不再尝试异步清理，避免 Windows 上 _sock.fileno() 错误刷屏。
        资源清理由 cleanup() 在 execute() 的 finally 块中完成。"""
        pass


# 保留原有WebSearchTools类以保持兼容性
class WebSearchTools(WebTools):
    """兼容性类,继承自WebTools"""

    def __init__(self, api_url: str = "http://localhost:8080"):
        # 创建一个虚拟的project_path和safety_guard
        from pathlib import Path

        class MockSafetyGuard:
            def is_safe_path(self, path):
                return True

        super().__init__(Path("."), MockSafetyGuard())

        # 如果提供了searxng URL,启用它
        if api_url:
            self.search_engines["searxng"]["url"] = api_url
            self.search_engines["searxng"]["enabled"] = True

    async def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """兼容性方法"""
        result = await self.search_web(query, engine="searxng", max_results=max_results)

        # 转换为旧格式
        if result.get("success"):
            return {
                "success": True,
                "query": query,
                "results": result.get("results", []),
                "count": len(result.get("results", [])),
            }
        else:
            return {"error": result.get("error", "搜索失败"), "success": False}
