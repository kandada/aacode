"""
网页抓取技能实现
"""
import aiohttp
import asyncio
import ssl
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse
import re
import html
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("web_scraper")


async def scrape_web(url: str,
                     operations: List[str],
                     selector: Optional[str] = None,
                     max_pages: int = 1,
                     timeout: int = 30) -> Dict[str, Any]:
    """
    抓取网页内容

    Args:
        url: 目标URL
        operations: 要执行的操作列表
        selector: CSS选择器（用于提取特定元素）
        max_pages: 最大抓取页数
        timeout: 超时时间

    Returns:
        抓取结果
    """
    try:
        # 验证URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return {"success": False, "error": f"无效的URL: {url}"}

        operations_performed = []
        scraped_data = []
        all_links = []

        # 抓取页面
        for page_num in range(max_pages):
            if page_num > 0 and not all_links:
                break

            current_url = all_links[page_num] if page_num > 0 else url

            logger.info(f"抓取页面 {page_num + 1}/{max_pages}: {current_url}")

            page_data = await _fetch_page(current_url, timeout)
            if not page_data.get("success"):
                return page_data

            html_content = page_data.get("content", "")
            page_url = page_data.get("url", current_url)

            # 解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            page_result = {
                "url": page_url,
                "title": _extract_title(soup),
                "operations": []
            }

            for op in operations:
                if op == "extract_text":
                    text_data = await _extract_text(soup, selector)
                    page_result["operations"].append({
                        "name": "extract_text",
                        "data": text_data
                    })
                    operations_performed.append(f"提取文本: {len(text_data.get('text', ''))} 字符")

                elif op == "extract_links":
                    links_data = await _extract_links(soup, page_url)
                    page_result["operations"].append({
                        "name": "extract_links",
                        "data": links_data
                    })
                    all_links.extend(links_data.get("internal_links", []))
                    operations_performed.append(f"提取链接: {len(links_data.get('all_links', []))} 个")

                elif op == "extract_images":
                    images_data = await _extract_images(soup, page_url)
                    page_result["operations"].append({
                        "name": "extract_images",
                        "data": images_data
                    })
                    operations_performed.append(f"提取图片: {len(images_data.get('images', []))} 个")

                elif op == "extract_tables":
                    tables_data = await _extract_tables(soup)
                    page_result["operations"].append({
                        "name": "extract_tables",
                        "data": tables_data
                    })
                    operations_performed.append(f"提取表格: {len(tables_data.get('tables', []))} 个")

                elif op == "extract_metadata":
                    metadata = await _extract_metadata(soup)
                    page_result["operations"].append({
                        "name": "extract_metadata",
                        "data": metadata
                    })
                    operations_performed.append("提取元数据")

                elif op == "clean_content":
                    cleaned = await _clean_content(html_content)
                    page_result["operations"].append({
                        "name": "clean_content",
                        "data": cleaned
                    })
                    operations_performed.append(f"清理内容: {cleaned.get('char_count', 0)} 字符")

            scraped_data.append(page_result)

            # 如果只需要一页，就停止
            if max_pages == 1:
                break

        # 去重链接
        unique_links = list(set(all_links))

        return {
            "success": True,
            "url": url,
            "pages_scraped": len(scraped_data),
            "operations_performed": operations_performed,
            "scraped_data": scraped_data,
            "total_links_found": len(unique_links),
            "sample_links": unique_links[:10]  # 只返回前10个链接作为示例
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _fetch_page(url: str, timeout: int) -> Dict[str, Any]:
    """获取页面内容"""
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # 创建SSL上下文，禁用证书验证（仅用于测试）
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(
            timeout=timeout_obj,
            connector=connector
        ) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP错误: {response.status}",
                        "status_code": response.status
                    }

                content = await response.text()
                return {
                    "success": True,
                    "content": content,
                    "url": str(response.url),
                    "status_code": response.status,
                    "content_type": response.headers.get("Content-Type", "")
                }

    except aiohttp.ClientError as e:
        return {"success": False, "error": f"网络错误: {str(e)}"}
    except asyncio.TimeoutError:
        return {"success": False, "error": f"请求超时: {timeout}秒"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_title(soup: BeautifulSoup) -> str:
    """提取页面标题"""
    title_tag = soup.find('title')
    if title_tag:
        return title_tag.get_text(strip=True)

    # 尝试从h1标签获取
    h1_tag = soup.find('h1')
    if h1_tag:
        return h1_tag.get_text(strip=True)

    return ""


async def _extract_text(soup: BeautifulSoup, selector: Optional[str] = None) -> Dict[str, Any]:
    """提取文本内容"""
    try:
        if selector:
            elements = soup.select(selector)
            texts = [elem.get_text(strip=True) for elem in elements if elem.get_text(strip=True)]
            full_text = ' '.join(texts)
        else:
            # 提取主要文本内容
            # 移除脚本和样式
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # 获取所有文本
            texts = soup.stripped_strings
            full_text = ' '.join(texts)

        # 清理文本
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        # 提取段落
        paragraphs = []
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 10:  # 只保留有内容的段落
                paragraphs.append(text)

        return {
            "full_text": full_text[:5000],  # 限制长度
            "text_length": len(full_text),
            "paragraphs": paragraphs[:20],  # 只返回前20个段落
            "paragraph_count": len(paragraphs)
        }

    except Exception as e:
        return {"error": str(e), "full_text": "", "paragraphs": []}


async def _extract_links(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """提取链接"""
    try:
        all_links = []
        internal_links = []
        external_links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                continue

            # 处理相对URL
            full_url = urljoin(base_url, href)

            link_info = {
                "url": full_url,
                "text": a_tag.get_text(strip=True)[:100],
                "title": a_tag.get('title', '')
            }

            all_links.append(link_info)

            # 分类链接
            parsed_base = urlparse(base_url)
            parsed_link = urlparse(full_url)

            if parsed_link.netloc == parsed_base.netloc:
                internal_links.append(full_url)
            else:
                external_links.append(full_url)

        return {
            "all_links": all_links[:50],  # 只返回前50个链接
            "internal_links": list(set(internal_links))[:20],
            "external_links": list(set(external_links))[:20],
            "total_count": len(all_links),
            "internal_count": len(internal_links),
            "external_count": len(external_links)
        }

    except Exception as e:
        return {"error": str(e), "all_links": [], "internal_links": [], "external_links": []}


async def _extract_images(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """提取图片"""
    try:
        images = []

        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src'].strip()
            if not src:
                continue

            # 处理相对URL
            full_src = urljoin(base_url, src)

            img_info = {
                "src": full_src,
                "alt": img_tag.get('alt', ''),
                "title": img_tag.get('title', ''),
                "width": img_tag.get('width'),
                "height": img_tag.get('height')
            }

            images.append(img_info)

        return {
            "images": images[:30],  # 只返回前30张图片
            "total_count": len(images)
        }

    except Exception as e:
        return {"error": str(e), "images": []}


async def _extract_tables(soup: BeautifulSoup) -> Dict[str, Any]:
    """提取表格数据"""
    try:
        tables = []

        for table_idx, table_tag in enumerate(soup.find_all('table')):
            table_data = {
                "index": table_idx,
                "rows": []
            }

            # 提取表头
            headers = []
            thead = table_tag.find('thead')
            if thead:
                for th in thead.find_all('th'):
                    headers.append(th.get_text(strip=True))
            else:
                # 如果没有thead，尝试从第一行获取表头
                first_row = table_tag.find('tr')
                if first_row:
                    for th in first_row.find_all(['th', 'td']):
                        headers.append(th.get_text(strip=True))

            table_data["headers"] = headers

            # 提取表格行
            rows = []
            for tr in table_tag.find_all('tr'):
                row_cells = []
                for td in tr.find_all('td'):
                    row_cells.append(td.get_text(strip=True))

                if row_cells:  # 只添加有数据的行
                    rows.append(row_cells)

            table_data["rows"] = rows
            table_data["row_count"] = len(rows)
            table_data["col_count"] = len(headers) if headers else (len(rows[0]) if rows else 0)

            tables.append(table_data)

        return {
            "tables": tables[:10],  # 只返回前10个表格
            "total_count": len(tables)
        }

    except Exception as e:
        return {"error": str(e), "tables": []}


async def _extract_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """提取元数据"""
    try:
        metadata = {}

        # 提取meta标签
        meta_tags = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                meta_tags[name] = content

        metadata["meta_tags"] = meta_tags

        # 提取Open Graph数据
        og_data = {}
        for meta in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
            og_data[meta['property']] = meta.get('content', '')

        metadata["og_data"] = og_data

        # 提取JSON-LD数据
        json_ld_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                import json
                data = json.loads(script.string)
                json_ld_data.append(data)
            except:
                pass

        metadata["json_ld"] = json_ld_data

        # 提取其他信息
        metadata["language"] = soup.get('lang') or soup.find('html').get('lang', '')
        metadata["charset"] = soup.find('meta', charset=True)
        if metadata["charset"]:
            metadata["charset"] = metadata["charset"]["charset"]

        return metadata

    except Exception as e:
        return {"error": str(e)}


async def _clean_content(html_content: str) -> Dict[str, Any]:
    """清理HTML内容"""
    try:
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', html_content)

        # 解码HTML实体
        text = html.unescape(text)

        # 移除多余空白
        text = re.sub(r'\s+', ' ', text).strip()

        # 提取句子
        sentences = re.split(r'[.!?。！？]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        return {
            "cleaned_text": text[:2000],  # 限制长度
            "char_count": len(text),
            "sentence_count": len(sentences),
            "sentences": sentences[:20]  # 只返回前20个句子
        }

    except Exception as e:
        return {"error": str(e), "cleaned_text": "", "char_count": 0, "sentences": []}


async def scrape_multiple(urls: List[str],
                          operations: List[str],
                          concurrency: int = 3,
                          timeout: int = 30) -> Dict[str, Any]:
    """
    并发抓取多个URL

    Args:
        urls: URL列表
        operations: 要执行的操作列表
        concurrency: 并发数
        timeout: 超时时间

    Returns:
        抓取结果
    """
    try:
        if not urls:
            return {"success": False, "error": "URL列表不能为空"}

        results = []
        failed_urls = []

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_semaphore(url):
            async with semaphore:
                try:
                    result = await scrape_web(url, operations, timeout=timeout)
                    return {"url": url, "result": result}
                except Exception as e:
                    return {"url": url, "error": str(e)}

        # 并发抓取
        tasks = [fetch_with_semaphore(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for response in responses:
            if isinstance(response, Exception):
                failed_urls.append({"error": str(response)})
                continue

            url = response.get("url")
            result = response.get("result")

            if result and result.get("success"):
                results.append({
                    "url": url,
                    "success": True,
                    "data": result
                })
            else:
                failed_urls.append({
                    "url": url,
                    "error": result.get("error") if result else "未知错误"
                })

        return {
            "success": True,
            "total_urls": len(urls),
            "successful": len(results),
            "failed": len(failed_urls),
            "results": results,
            "failed_urls": failed_urls[:10]  # 只返回前10个失败URL
        }

    except Exception as e:
        return {"success": False, "error": str(e)}