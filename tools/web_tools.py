from __future__ import annotations

# tools/web_tools.py
"""
网络搜索工具实现
支持 searXNG / Brave Search / Google CSE / Bing / SerpAPI
通过 URL 自动识别引擎类型，填入对应 URL 即可使用
"""

import asyncio
import aiohttp
import uuid
from pathlib import Path
import json
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import quote, urljoin
import os
import time
from aacode.i18n import t


def _detect_engine_type(url: str) -> str:
    """通过 URL 自动识别搜索引擎类型"""
    if not url:
        return "searxng"
    url_lower = url.lower()
    if "brave.com" in url_lower:
        return "brave"
    if "googleapis.com/customsearch" in url_lower:
        return "google_cse"
    if "bing.microsoft.com" in url_lower:
        return "bing"
    if "serpapi.com" in url_lower:
        return "serpapi"
    return "searxng"


class WebTools:
    """网络搜索和Web操作工具（searXNG / Brave / Google CSE / Bing / SerpAPI）"""

    def __init__(self, project_path: Path, safety_guard):
        self.project_path = project_path
        self.safety_guard = safety_guard
        self.session: Optional[aiohttp.ClientSession] = None

        # settings.tools.search_api_url 已在 Settings.__init__ 中融合了
        # "env 覆盖 YAML" 的结果，直接信任它。env var 仅作为 settings 不可用时的兜底。
        env_url = os.getenv("SEARCHXNG_URL")
        config_url = None
        enable_web_search = True
        generic_api_key = None
        enable_fallback = True
        try:
            if __package__ in (None, ""):
                from config import settings
            else:
                from ..config import settings
            config_url = settings.tools.search_api_url
            enable_web_search = settings.tools.enable_web_search
            generic_api_key = settings.tools.search_api_key
            enable_fallback = settings.tools.enable_fallback_scrape
        except Exception:
            pass

        if config_url:
            base_url = config_url.rstrip("/search")
        elif env_url:
            base_url = env_url.rstrip("/search")
        else:
            base_url = "http://localhost:8080"

        enabled = bool(config_url or env_url) and enable_web_search

        engine_type = _detect_engine_type(base_url)

        def _api_key(env_name):
            return os.getenv(env_name) or generic_api_key or ""

        self.search_engines = {
            "searxng": {
                "url": base_url,
                "enabled": enabled and engine_type == "searxng",
                "description": "Self-hosted search engine aggregator (integrates Google, Bing, Baidu, Sogou, etc.)",
            },
            "brave": {
                "url": base_url,
                "enabled": enabled and engine_type == "brave",
                "api_key": _api_key("BRAVE_API_KEY"),
                "description": "Brave Search API (2000 queries/month free, independent index)",
            },
            "google_cse": {
                "url": base_url,
                "enabled": enabled and engine_type == "google_cse",
                "api_key": _api_key("GOOGLE_API_KEY"),
                "cx": os.getenv("GOOGLE_CSE_CX", ""),
                "description": "Google Custom Search JSON API (100 queries/day free)",
            },
            "bing": {
                "url": base_url,
                "enabled": enabled and engine_type == "bing",
                "api_key": _api_key("BING_API_KEY"),
                "description": "Bing Web Search API (1000 queries/month free)",
            },
            "serpapi": {
                "url": base_url,
                "enabled": enabled and engine_type == "serpapi",
                "api_key": _api_key("SERPAPI_API_KEY"),
                "description": "SerpAPI search aggregator (supports Google, Bing, etc.)",
            },
            "_engine_type": engine_type,
            "_enable_fallback": enable_fallback,
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
        timeout: int = 8,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        网络搜索（只支持searxng）

        Args:
            query: 搜索查询
            engine: 搜索引擎 (只支持searxng或auto)
            max_results: 最大结果数
            safe_search: 是否启用安全搜索
            timeout: 搜索超时时间(秒)，默认8秒

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
                    "error": f"search engine {engine} unavailable",
                    "available_engines": [
                        k for k, v in self.search_engines.items()
                        if isinstance(v, dict) and v.get("enabled")
                    ],
                }

            # 速率限制 — 内部等待而非报错
            await self._enforce_rate_limit(engine)

            # 执行搜索
            results = await self._search_with_fallback(
                query, engine, max_results, safe_search, timeout
            )

            # 更新速率限制
            if results.get("success"):
                used_engine = results.get("engine", engine)
                self.last_search_time[used_engine] = time.time()

            return results

        except Exception as e:
            return {"success": False, "error": f"Search failed: {str(e)}"}

    async def fetch_url(
        self,
        url: str,
        timeout: Optional[int] = None,
        max_content_length: int = 5000,
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
                return {"success": False, "error": "URL safety check failed"}

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
                        "error": f"unsupported content type: {content_type}",
                    }

                raw_content = await response.text(errors="ignore")
                raw_length = len(raw_content)

                # 保存原始完整内容到文件（供后续 grep 使用）
                extracts = self.project_path / ".aacode" / "extracts"
                extracts.mkdir(parents=True, exist_ok=True)
                file_path = extracts / f"tool_content_{uuid.uuid4().hex[:8]}.txt"
                file_path.write_text(raw_content, encoding="utf-8")

                # 检测 JS 重定向并自动跟随（Cloudflare / SPA 页面）
                redirect_url = self._detect_js_redirect(raw_content, url)
                if redirect_url:
                    redirect_result = await self._follow_redirect(
                        redirect_url, timeout, max_content_length
                    )
                    if redirect_result.get("success"):
                        return redirect_result

                # 清洗 HTML：去除 script/style/head 等垃圾，提取纯文本
                cleaned = self._clean_html(raw_content)
                cleaned_length = len(cleaned)

                # 对清洗后的纯文本做截断
                if cleaned_length > max_content_length:
                    content = cleaned[:max_content_length]
                    suffix = f"\n\n[Full cleaned text ({cleaned_length} chars) saved to {file_path}. Raw HTML ({raw_length} bytes) also saved. Use run_shell to read the file for what you need.]"
                    content += suffix
                else:
                    content = cleaned

                # 清洗后无有效文本时附加警告
                content_warning = None
                if cleaned_length < 50 and raw_length > 2000:
                    content_warning = (
                        "[WARNING: This page appears to be dynamically rendered (SPA) or heavily scripted. "
                        f"Only {cleaned_length} chars of visible text extracted from {raw_length} bytes of HTML. "
                        "Consider using search_web to find alternative sources.]"
                    )

                result = {
                    "success": True,
                    "url": url,
                    "status_code": response.status,
                    "content_type": content_type,
                    "content_length": cleaned_length,
                    "raw_length": raw_length,
                    "content": content,
                }
                if content_warning:
                    result["content_warning"] = content_warning
                    result["content"] = content_warning + "\n\n" + content
                return result

        except asyncio.TimeoutError:
            return {"success": False, "error": f"request timeout ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": f"Fetch web page failed: {str(e)}"}

    @staticmethod
    def _clean_html(html: str) -> str:
        """清洗 HTML：去除 script/style/head 标签，提取可见纯文本。"""
        import re
        # 移除整段 <script>...</script>
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除整段 <style>...</style>
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除 <head>...</head>
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除所有剩余 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', html)
        # 解码 HTML 实体
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#8211;', '–').replace('&#8212;', '—')
        text = text.replace('&hellip;', '…').replace('&#8216;', "'").replace('&#8217;', "'")
        # 合并空白
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _detect_js_redirect(html: str, original_url: str) -> Optional[str]:
        """检测 JS 重定向页面，返回重定向目标 URL 或 None。"""
        import re
        from urllib.parse import urljoin
        # location.replace("...") / location.href("...")
        m = re.search(r'location\.(?:replace|href)\s*\(\s*["\']([^"\']+)["\']', html)
        if m:
            return urljoin(original_url, m.group(1))
        # location.href = "..."
        m = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', html)
        if m:
            return urljoin(original_url, m.group(1))
        # <meta http-equiv="refresh">
        m = re.search(r'<meta[^>]+http-equiv\s*=\s*["\']?refresh["\']?[^>]+content\s*=\s*["\']?\d+\s*;\s*url\s*=\s*([^\s"\'<>]+)', html, re.IGNORECASE)
        if m:
            return urljoin(original_url, m.group(1))
        return None

    async def _follow_redirect(
        self,
        redirect_url: str,
        timeout: Optional[int],
        max_content_length: int,
    ) -> Dict[str, Any]:
        """跟随 JS 重定向链，最多 5 跳。"""
        import re
        visited = set()
        current_url = redirect_url
        for _ in range(5):
            if current_url in visited:
                break
            visited.add(current_url)
            try:
                await self._ensure_session()
                session = self.session
                assert session is not None
                client_timeout = aiohttp.ClientTimeout(total=timeout or 30)
                async with session.get(current_url, timeout=client_timeout) as resp:
                    ct = resp.headers.get("content-type", "").lower()
                    if not any(t in ct for t in ["text/html", "text/plain", "application/json"]):
                        break
                    raw = await resp.text(errors="ignore")
                    cleaned = self._clean_html(raw)
                    if len(cleaned) >= 200:
                        return {
                            "success": True,
                            "url": resp.url.human_repr() if hasattr(resp.url, 'human_repr') else str(resp.url),
                            "status_code": resp.status,
                            "content_type": ct,
                            "content_length": len(cleaned),
                            "content": cleaned[:max_content_length],
                        }
                    next_url = self._detect_js_redirect(raw, current_url)
                    if not next_url:
                        return {
                            "success": True,
                            "url": resp.url.human_repr() if hasattr(resp.url, 'human_repr') else str(resp.url),
                            "status_code": resp.status,
                            "content_type": ct,
                            "content_length": len(cleaned),
                            "content": cleaned[:max_content_length],
                        }
                    current_url = next_url
            except Exception:
                break
        return {"success": False, "error": f"JS redirect chain exhausted after {len(visited)} hops"}

    def _choose_best_engine(self) -> str:
        """选择最佳搜索引擎"""
        engine_type = self.search_engines.get("_engine_type", "searxng")
        if engine_type in self.search_engines and self.search_engines[engine_type].get("enabled", False):
            return engine_type
        if self.search_engines.get("searxng", {}).get("enabled", False):
            return "searxng"
        return ""

    async def _search_with_fallback(
        self, query: str, engine: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """搜索实现，根据引擎类型路由"""
        if engine == "auto":
            engine = self._choose_best_engine()
        if not engine:
            return {
                "success": False,
                "error": "no search engine available",
                "query": query,
            }

        engine_entry = self.search_engines.get(engine, {})
        if not engine_entry.get("enabled", False):
            desc = engine_entry.get("description", engine)
            return {
                "success": False,
                "error": f"search engine {engine} not enabled",
                "query": query,
                "suggestion": f"Engine: {desc}. "
                "Please configure tools.search_api_url in aacode_config.yaml or set SEARCHXNG_URL environment variable",
            }

        try:
            print(f"🔍 Using search engine: {engine}")
            search_methods = {
                "searxng": self._search_searxng,
                "brave": self._search_brave,
                "google_cse": self._search_google_cse,
                "bing": self._search_bing,
                "serpapi": self._search_serpapi,
            }
            method = search_methods.get(engine)
            if method:
                result = await method(query, max_results, safe_search, timeout)
                if result.get("success"):
                    return result
            else:
                result = {
                    "success": False,
                    "error": f"unsupported engine: {engine}",
                    "query": query,
                }

            fallback_result = await self._search_fallback_scrape(query, max_results, timeout)
            if fallback_result.get("success"):
                return fallback_result
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"search failed: {str(e)}",
                "query": query,
            }

    async def _enforce_rate_limit(self, engine: str):
        """速率限制 — 内部等待，对调用方透明"""
        last_time = self.last_search_time.get(engine, 0)
        rate_limit_value = self.search_engines.get(engine, {}).get("rate_limit", 1.0)

        try:
            rate_limit = float(rate_limit_value)
        except (ValueError, TypeError):
            rate_limit = 1.0

        if engine == "searxng":
            rate_limit = 0.5

        wait = rate_limit - (time.time() - last_time)
        if wait > 0:
            await asyncio.sleep(wait)

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
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """使用searXNG搜索（多参数变体重试，每个请求独立超时）"""
        return await self._search_searxng_inner(query, max_results, safe_search, timeout)

    async def _search_searxng_inner(
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
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

            # 尝试不同的参数组合（精简为 2 个，减少无谓重试）
            param_variations = [
                base_params,  # 标准参数（大多数 SearXNG 实例适用）
                {**base_params, "engines": "google,duckduckgo,bing"},  # 兜底：显式指定引擎
            ]

            # 使用传入的 timeout 作为单次请求超时
            per_request_timeout = aiohttp.ClientTimeout(total=timeout)

            errors = []
            for i, test_params in enumerate(param_variations):
                try:
                    print(f"🔍 Trying param combo {i+1}: {test_params}")
                    if self.session is None:
                        await self._ensure_session()
                    session = self.session
                    assert session is not None, "Session should be initialized"
                    async with session.get(
                        search_url, params=test_params, timeout=per_request_timeout
                    ) as response:
                        if response.status == 200:
                            content_type = response.headers.get(
                                "content-type", ""
                            ).lower()

                            if "application/json" in content_type:
                                data = await response.json()

                                if data.get("error"):
                                    errors.append(f"combo {i+1}: SearXNG error: {data.get('error')}")
                                    continue

                                results = data.get("results", [])
                                if not results:
                                    errors.append(f"combo {i+1}: empty results")
                                    continue

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
                                errors.append(f"combo {i+1}: non-JSON response ({content_type[:50]})")
                                continue

                        else:
                            errors.append(f"combo {i+1}: HTTP {response.status}")
                            continue

                except asyncio.TimeoutError:
                    errors.append(f"combo {i+1}: timeout after {timeout}s")
                    continue
                except Exception as e:
                    errors.append(f"combo {i+1}: {str(e)}")
                    continue

            return {
                "success": False,
                "error": f"SearXNG search failed: {'; '.join(errors)}" if errors else "SearXNG search failed: all variations exhausted",
                "query": query,
                "suggestion": "Please check searXNG configuration and network connection",
            }

        except Exception as e:
            return {"success": False, "error": f"SearXNGSearch failed: {str(e)}"}

    async def _search_brave(
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """Brave Search API"""
        api_key = self.search_engines.get("brave", {}).get("api_key", "")
        if not api_key:
            return {"success": False, "error": "Brave API key not set (env: BRAVE_API_KEY)", "query": query}
        try:
            return await asyncio.wait_for(
                self._search_brave_inner(query, max_results, safe_search, timeout, api_key),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Brave search timed out after {timeout}s", "query": query}
        except Exception as e:
            return {"success": False, "error": f"Brave search failed: {str(e)}"}

    async def _search_brave_inner(self, query, max_results, safe_search, timeout, api_key):
        search_url = "https://api.search.brave.com/res/v1/web/search"
        params = {"q": query, "count": min(max_results, 20), "safesearch": "strict" if safe_search else "off"}
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": api_key}
        await self._ensure_session()
        session = self.session
        assert session is not None
        async with session.get(search_url, params=params, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"Brave HTTP {resp.status}", "query": query}
            data = await resp.json()
            results = []
            for r in data.get("web", {}).get("results", [])[:max_results]:
                results.append({"title": r.get("title", ""), "url": r.get("url", ""),
                                "content": r.get("description", ""), "engine": "brave", "score": 0})
            return {"success": True, "engine": "brave", "query": query,
                    "results": results, "total_results": len(results)}

    async def _search_google_cse(
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """Google Custom Search JSON API"""
        cfg = self.search_engines.get("google_cse", {})
        api_key = cfg.get("api_key", "")
        cx = cfg.get("cx", "")
        if not api_key:
            return {"success": False, "error": "Google API key not set (env: GOOGLE_API_KEY)", "query": query}
        if not cx:
            return {"success": False, "error": "Google CSE CX not set (env: GOOGLE_CSE_CX)", "query": query}
        try:
            return await asyncio.wait_for(
                self._search_google_cse_inner(query, max_results, safe_search, timeout, api_key, cx),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Google CSE search timed out after {timeout}s", "query": query}
        except Exception as e:
            return {"success": False, "error": f"Google CSE search failed: {str(e)}"}

    async def _search_google_cse_inner(self, query, max_results, safe_search, timeout, api_key, cx):
        search_url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx, "q": query, "num": min(max_results, 10),
                  "safe": "active" if safe_search else "off"}
        await self._ensure_session()
        session = self.session
        assert session is not None
        async with session.get(search_url, params=params,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"Google CSE HTTP {resp.status}", "query": query}
            data = await resp.json()
            results = []
            for r in data.get("items", [])[:max_results]:
                results.append({"title": r.get("title", ""), "url": r.get("link", ""),
                                "content": r.get("snippet", ""), "engine": "google_cse", "score": 0})
            return {"success": True, "engine": "google_cse", "query": query,
                    "results": results, "total_results": len(results)}

    async def _search_bing(
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """Bing Web Search API"""
        api_key = self.search_engines.get("bing", {}).get("api_key", "")
        if not api_key:
            return {"success": False, "error": "Bing API key not set (env: BING_API_KEY)", "query": query}
        try:
            return await asyncio.wait_for(
                self._search_bing_inner(query, max_results, safe_search, timeout, api_key),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Bing search timed out after {timeout}s", "query": query}
        except Exception as e:
            return {"success": False, "error": f"Bing search failed: {str(e)}"}

    async def _search_bing_inner(self, query, max_results, safe_search, timeout, api_key):
        search_url = "https://api.bing.microsoft.com/v7.0/search"
        params = {"q": query, "count": min(max_results, 50),
                  "safeSearch": "Strict" if safe_search else "Off"}
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        await self._ensure_session()
        session = self.session
        assert session is not None
        async with session.get(search_url, params=params, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"Bing HTTP {resp.status}", "query": query}
            data = await resp.json()
            results = []
            for r in data.get("webPages", {}).get("value", [])[:max_results]:
                results.append({"title": r.get("name", ""), "url": r.get("url", ""),
                                "content": r.get("snippet", ""), "engine": "bing", "score": 0})
            return {"success": True, "engine": "bing", "query": query,
                    "results": results, "total_results": len(results)}

    async def _search_serpapi(
        self, query: str, max_results: int, safe_search: bool, timeout: int = 8
    ) -> Dict[str, Any]:
        """SerpAPI search aggregator"""
        api_key = self.search_engines.get("serpapi", {}).get("api_key", "")
        if not api_key:
            return {"success": False, "error": "SerpAPI key not set (env: SERPAPI_API_KEY)", "query": query}
        try:
            return await asyncio.wait_for(
                self._search_serpapi_inner(query, max_results, safe_search, timeout, api_key),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"SerpAPI search timed out after {timeout}s", "query": query}
        except Exception as e:
            return {"success": False, "error": f"SerpAPI search failed: {str(e)}"}

    async def _search_serpapi_inner(self, query, max_results, safe_search, timeout, api_key):
        search_url = "https://serpapi.com/search"
        params = {"api_key": api_key, "q": query, "engine": "google",
                  "num": min(max_results, 100), "safe": "active" if safe_search else "off"}
        await self._ensure_session()
        session = self.session
        assert session is not None
        async with session.get(search_url, params=params,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"SerpAPI HTTP {resp.status}", "query": query}
            data = await resp.json()
            results = []
            for r in data.get("organic_results", [])[:max_results]:
                results.append({"title": r.get("title", ""), "url": r.get("link", ""),
                                "content": r.get("snippet", ""), "engine": "serpapi", "score": 0})
            return {"success": True, "engine": "serpapi", "query": query,
                    "results": results, "total_results": len(results)}

    async def _search_fallback_scrape(
        self, query: str, max_results: int, timeout: int = 8
    ) -> Dict[str, Any]:
        """兜底方案：直接抓取 Bing / Sogou 搜索结果页解析 HTML"""
        if not self.search_engines.get("_enable_fallback", True):
            return {"success": False, "error": "fallback scrape disabled", "query": query}

        import re

        scrapers = [
            {
                "name": "bing_scrape",
                "url": "https://www.bing.com/search",
                "params": {"q": query, "count": str(min(max_results, 20))},
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                "result_re": re.compile(
                    r'<li\s+class="b_algo"[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>\s*(.*?)\s*</a>.*?<p[^>]*>(.*?)</p>',
                    re.DOTALL | re.IGNORECASE,
                ),
                "clean_re": re.compile(r"<[^>]+>"),
            },
            {
                "name": "sogou_scrape",
                "url": "https://www.sogou.com/web",
                "params": {"query": query},
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                "result_re": re.compile(
                    r'<div[^>]*class="[^"]*vrwrap[^"]*"[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>\s*(.*?)\s*</a>.*?<p[^>]*>(.*?)</p>',
                    re.DOTALL | re.IGNORECASE,
                ),
                "clean_re": re.compile(r"<[^>]+>"),
            },
        ]

        import time as _time
        start_time = _time.time()

        for scraper in scrapers:
            remaining = timeout - (_time.time() - start_time)
            if remaining <= 0:
                break
            try:
                await self._ensure_session()
                session = self.session
                assert session is not None
                async with session.get(
                    scraper["url"],
                    params=scraper["params"],
                    headers=scraper["headers"],
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    matches = scraper["result_re"].findall(html)
                    if not matches:
                        continue
                    results = []
                    seen_urls = set()
                    for url, title, snippet in matches[:max_results]:
                        url = url.strip()
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        title = scraper["clean_re"].sub("", title).strip()
                        snippet = scraper["clean_re"].sub("", snippet).strip()
                        if title:
                            results.append({
                                "title": title,
                                "url": url,
                                "content": snippet,
                                "engine": scraper["name"],
                                "score": 0,
                            })
                    if results:
                        return {
                            "success": True,
                            "engine": scraper["name"],
                            "query": query,
                            "results": results,
                            "total_results": len(results),
                        }
            except Exception:
                continue

        return {"success": False, "error": "fallback scrape: no results from Bing or Sogou", "query": query}

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
            return {"error": result.get("error", "Search failed"), "success": False}

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
                        "error": f"GitHub API error: {response.status}",
                    }

        except Exception as e:
            return {"success": False, "error": f"Code search failed: {str(e)}"}

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
            return {"error": result.get("error", "Search failed"), "success": False}
