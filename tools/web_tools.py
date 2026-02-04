# 网络搜索工具
# tools/web_tools.py
"""
网络搜索工具实现
支持多种搜索引擎和网络API
"""
import asyncio
import aiohttp
import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import quote, urljoin
import os
import time


class WebTools:
    """网络搜索和Web操作工具"""
    
    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self.session = None
        self.search_engines = {
            "searxng": {
                "url": os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/search"),
                "enabled": bool(os.getenv("SEARXNG_URL"))
            },
            "duckduckgo": {
                "enabled": True,
                "rate_limit": 1.0  # 秒
            },
            "brave": {
                "enabled": bool(os.getenv("BRAVE_API_KEY")),
                "api_key": os.getenv("BRAVE_API_KEY"),
                "rate_limit": 1.0
            },
            "serpapi": {
                "enabled": bool(os.getenv("SERPAPI_KEY")),
                "api_key": os.getenv("SERPAPI_KEY"),
                "rate_limit": 1.0
            }
        }
        self.last_search_time = {}
        
    async def _ensure_session(self):
        """确保HTTP会话存在"""
        if self.session is None or self.session.closed:
            # 使用配置的超时时间(来自 aacode_config.yaml)
            from config import settings
            web_timeout = settings.timeouts.web_request
            timeout = aiohttp.ClientTimeout(total=web_timeout, connect=10)
            # 简化配置,不使用SSL context(对HTTP连接不需要)
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                force_close=False,
                enable_cleanup_closed=True
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
            )
    
    async def search_web(self, 
                        query: str, 
                        engine: str = "auto",
                        max_results: int = 10,
                        safe_search: bool = True,
                        **kwargs) -> Dict[str, Any]:
        """
        网络搜索
        
        Args:
            query: 搜索查询
            engine: 搜索引擎 (auto, searxng, duckduckgo, brave, serpapi)
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
                    "available_engines": [k for k, v in self.search_engines.items() if v.get("enabled")]
                }
            
            # 速率限制检查
            if not self._check_rate_limit(engine):
                return {
                    "success": False,
                    "error": f"搜索引擎 {engine} 速率限制中,请稍后重试"
                }
            
            # 执行搜索
            if engine == "searxng":
                results = await self._search_searxng(query, max_results, safe_search)
            elif engine == "duckduckgo":
                results = await self._search_duckduckgo(query, max_results)
            elif engine == "brave":
                results = await self._search_brave(query, max_results, safe_search)
            elif engine == "serpapi":
                results = await self._search_serpapi(query, max_results, safe_search)
            else:
                results = {"success": False, "error": f"不支持的搜索引擎: {engine}"}
            
            # 更新速率限制
            self.last_search_time[engine] = time.time()
            
            return results
            
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}"
            }
    
    async def fetch_url(self, 
                        url: str, 
                        timeout: int = None,
                        max_content_length: int = 100000,
                        **kwargs) -> Dict[str, Any]:
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
                from config import settings
                timeout = settings.timeouts.web_request
            
            await self._ensure_session()
            
            # URL安全检查
            if not self._is_safe_url(url):
                return {
                    "success": False,
                    "error": "URL安全检查失败"
                }
            
            async with self.session.get(url, timeout=timeout) as response:
                content_type = response.headers.get('content-type', '').lower()
                
                # 只处理文本内容
                if not any(ct in content_type for ct in ['text/html', 'text/plain', 'application/json']):
                    return {
                        "success": False,
                        "error": f"不支持的内容类型: {content_type}"
                    }
                
                content = await response.text(errors='ignore')
                
                # 限制内容长度
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "\n...[内容已截断]"
                
                return {
                    "success": True,
                    "url": url,
                    "status_code": response.status,
                    "content_type": content_type,
                    "content_length": len(content),
                    "content": content
                }
                
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"请求超时 ({timeout}秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取网页失败: {str(e)}"
            }
    
    async def search_code(self, 
                         query: str, 
                         language: str = "",
                         max_results: int = 10) -> Dict[str, Any]:
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
            
            headers = {}
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers['Authorization'] = f'token {github_token}'
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for item in data.get('items', []):
                        results.append({
                            "repository": item['repository']['full_name'],
                            "file": item['name'],
                            "path": item['path'],
                            "url": item['html_url'],
                            "description": item['repository'].get('description', ''),
                            "stars": item['repository'].get('stargazers_count', 0)
                        })
                    
                    return {
                        "success": True,
                        "query": query,
                        "language": language,
                        "results": results,
                        "total_count": data.get('total_count', 0)
                    }
                else:
                    return {
                        "success": False,
                        "error": f"GitHub API错误: {response.status}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"代码搜索失败: {str(e)}"
            }
    
    def _choose_best_engine(self) -> str:
        """选择最佳搜索引擎"""
        # 优先级:searxng > brave > serpapi > duckduckgo
        for engine in ["searxng", "brave", "serpapi", "duckduckgo"]:
            if self.search_engines.get(engine, {}).get("enabled", False):
                return engine
        return "duckduckgo"  # 默认
    
    def _check_rate_limit(self, engine: str) -> bool:
        """检查速率限制"""
        last_time = self.last_search_time.get(engine, 0)
        rate_limit = self.search_engines.get(engine, {}).get("rate_limit", 1.0)
        return time.time() - last_time >= rate_limit
    
    def _is_safe_url(self, url: str) -> bool:
        """URL安全检查"""
        try:
            # 基本URL格式检查
            if not url.startswith(('http://', 'https://')):
                return False
            
            # 检查是否为内网地址
            import ipaddress
            from urllib.parse import urlparse
            
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if not hostname:
                return False
            
            # 检查IP地址
            try:
                ip = ipaddress.ip_address(hostname)
                return not (ip.is_private or ip.is_loopback or ip.is_link_local)
            except ValueError:
                pass  # 不是IP地址,继续检查域名
            
            # 检查域名
            blocked_domains = ['localhost', '127.0.0.1', '0.0.0.0']
            if hostname in blocked_domains:
                return False
            
            # 检查端口
            if parsed.port and parsed.port not in [80, 443, 8080]:
                return False
            
            return True
            
        except Exception:
            return False
    
    async def _search_searxng(self, query: str, max_results: int, safe_search: bool) -> Dict[str, Any]:
        """使用SearXNG搜索"""
        try:
            base_url = self.search_engines["searxng"]["url"]
            search_url = f"{base_url}/search"
            
            # 根据用户的使用方法修正参数
            params = {
                'q': query,
                'format': 'json',
                'categories': 'general',  # 不是images
                'num_results': max_results,  # 使用num_results而不是count
                'language': 'zh-CN',
                'safesearch': 1 if safe_search else 0
            }
            
            async with self.session.get(search_url, params=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for result in data.get('results', [])[:max_results]:
                        results.append({
                            "title": result.get('title', ''),
                            "url": result.get('url', ''),
                            "content": result.get('content', ''),
                            "engine": result.get('engine', ''),
                            "score": result.get('score', 0)
                        })
                    
                    return {
                        "success": True,
                        "engine": "searxng",
                        "query": query,
                        "results": results,
                        "total_results": len(results)
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"SearXNG API错误: {response.status} - {error_text[:200]}"
                    }
                    
        except Exception as e:
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}"
            traceback_str = traceback.format_exc()
            return {
                "success": False,
                "error": f"SearXNG搜索失败: {error_detail}",
                "traceback": traceback_str
            }
    
    async def _search_duckduckgo(self, query: str, max_results: int) -> Dict[str, Any]:
        """使用DuckDuckGo即时回答API"""
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    
                    # 即时答案
                    abstract = data.get('Abstract', '')
                    if abstract:
                        results.append({
                            "title": data.get('Heading', ''),
                            "url": data.get('AbstractURL', ''),
                            "content": abstract,
                            "engine": "duckduckgo_instant",
                            "score": 1.0
                        })
                    
                    # 相关主题
                    for topic in data.get('RelatedTopics', [])[:max_results-1]:
                        if topic.get('Text'):
                            results.append({
                                "title": topic.get('FirstURL', '').split('/')[-1].replace('_', ' '),
                                "url": topic.get('FirstURL', ''),
                                "content": topic.get('Text', ''),
                                "engine": "duckduckgo_related",
                                "score": 0.8
                            })
                    
                    return {
                        "success": True,
                        "engine": "duckduckgo",
                        "query": query,
                        "results": results[:max_results],
                        "total_results": len(results)
                    }
                else:
                    return {
                        "success": False,
                        "error": f"DuckDuckGo API错误: {response.status}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"DuckDuckGo搜索失败: {str(e)}"
            }
    
    async def _search_brave(self, query: str, max_results: int, safe_search: bool) -> Dict[str, Any]:
        """使用Brave搜索API"""
        try:
            api_key = self.search_engines["brave"]["api_key"]
            url = "https://api.search.brave.com/res/v1/web/search"
            
            params = {
                'q': query,
                'count': max_results,
                'safesearch': 'moderate' if safe_search else 'off',
                'text_decorations': '0',
                'spellcheck': '1',
                'result_filter': 'web',
                'freshness': 'pd'
            }
            
            headers = {
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip',
                'X-Subscription-Token': api_key
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for item in data.get('web', {}).get('results', []):
                        results.append({
                            "title": item.get('title', ''),
                            "url": item.get('url', ''),
                            "content": item.get('description', ''),
                            "engine": "brave",
                            "score": 0
                        })
                    
                    return {
                        "success": True,
                        "engine": "brave",
                        "query": query,
                        "results": results,
                        "total_results": len(results)
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Brave API错误: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Brave搜索失败: {str(e)}"
            }
    
    async def _search_serpapi(self, query: str, max_results: int, safe_search: bool) -> Dict[str, Any]:
        """使用SerpAPI搜索"""
        try:
            api_key = self.search_engines["serpapi"]["api_key"]
            url = "https://serpapi.com/search"
            
            params = {
                'engine': 'google',
                'q': query,
                'api_key': api_key,
                'num': max_results,
                'safe': 'active' if safe_search else 'off',
                'hl': 'zh-CN',
                'gl': 'cn'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for item in data.get('organic_results', []):
                        results.append({
                            "title": item.get('title', ''),
                            "url": item.get('link', ''),
                            "content": item.get('snippet', ''),
                            "engine": "serpapi_google",
                            "score": 0
                        })
                    
                    return {
                        "success": True,
                        "engine": "serpapi_google",
                        "query": query,
                        "results": results,
                        "total_results": len(results)
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"SerpAPI错误: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"SerpAPI搜索失败: {str(e)}"
            }
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()


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
                "count": len(result.get("results", []))
            }
        else:
            return {
                "error": result.get("error", "搜索失败"),
                "success": False
            }