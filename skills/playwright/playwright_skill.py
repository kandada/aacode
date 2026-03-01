"""
Playwright浏览器自动化Skill - 支持浏览器自动化、动态网页处理、前端测试等能力
跨平台兼容版本，支持macOS、Linux、Windows系统
"""
import asyncio
import logging
import os
import sys
import platform
import functools
import subprocess
import shutil
from typing import Dict, Any, Optional, List, Tuple, Union
from urllib.parse import urlparse
from dataclasses import dataclass
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("playwright_skill")


class BrowserType(Enum):
    """支持的浏览器类型"""
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class PlatformType(Enum):
    """操作系统类型"""
    MACOS = "macos"
    LINUX = "linux"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


@dataclass
class BrowserInfo:
    """浏览器信息"""
    type: BrowserType
    executable_path: str
    version: Optional[str] = None
    installed: bool = False
    is_playwright_managed: bool = False


def _with_retry(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def _wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(f"{func.__name__} 第 {attempt + 1} 次失败，{delay}秒后重试: {str(e)}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} 重试 {max_retries} 次后失败: {str(e)}")
            return {"success": False, "error": str(last_error)}
        return _wrapper
    return decorator


def _get_platform() -> PlatformType:
    """获取当前操作系统平台"""
    system = platform.system().lower()
    if system == "darwin":
        return PlatformType.MACOS
    elif system == "linux":
        return PlatformType.LINUX
    elif system == "windows":
        return PlatformType.WINDOWS
    else:
        return PlatformType.UNKNOWN


def _get_default_browser_paths() -> Dict[BrowserType, List[str]]:
    """获取各平台默认浏览器路径"""
    platform_type = _get_platform()
    
    paths = {
        BrowserType.CHROME: [],
        BrowserType.CHROMIUM: [],
        BrowserType.FIREFOX: [],
        BrowserType.WEBKIT: []
    }
    
    if platform_type == PlatformType.MACOS:
        paths[BrowserType.CHROME] = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"
        ]
        paths[BrowserType.FIREFOX] = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            "/Applications/Firefox Developer Edition.app/Contents/MacOS/firefox"
        ]
        
    elif platform_type == PlatformType.LINUX:
        paths[BrowserType.CHROME] = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/opt/google/chrome/google-chrome"
        ]
        paths[BrowserType.CHROMIUM] = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/local/bin/chromium"
        ]
        paths[BrowserType.FIREFOX] = [
            "/usr/bin/firefox",
            "/usr/local/bin/firefox"
        ]
        
    elif platform_type == PlatformType.WINDOWS:
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        
        paths[BrowserType.CHROME] = [
            os.path.join(program_files, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google\\Chrome\\Application\\chrome.exe")
        ]
        paths[BrowserType.CHROMIUM] = [
            os.path.join(program_files, "Chromium\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Chromium\\Application\\chrome.exe")
        ]
        paths[BrowserType.FIREFOX] = [
            os.path.join(program_files, "Mozilla Firefox\\firefox.exe"),
            os.path.join(program_files_x86, "Mozilla Firefox\\firefox.exe")
        ]
    
    return paths


def _check_command_exists(cmd: str) -> bool:
    """检查命令是否存在"""
    try:
        return shutil.which(cmd) is not None
    except:
        return False


def _get_browser_version(executable_path: str) -> Optional[str]:
    """获取浏览器版本"""
    try:
        if _get_platform() == PlatformType.WINDOWS:
            # Windows使用wmic获取版本
            result = subprocess.run(
                ["wmic", "datafile", "where", f"name='{executable_path.replace('/', '\\\\')}'", "get", "Version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        else:
            # macOS/Linux使用--version参数
            result = subprocess.run(
                [executable_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 提取版本号
                import re
                version_match = re.search(r'(\d+\.\d+\.\d+\.\d+|\d+\.\d+\.\d+)', result.stdout)
                if version_match:
                    return version_match.group(1)
    except Exception as e:
        logger.debug(f"获取浏览器版本失败 {executable_path}: {e}")
    
    return None


def _detect_installed_browsers() -> List[BrowserInfo]:
    """检测系统已安装的浏览器"""
    browsers = []
    default_paths = _get_default_browser_paths()
    
    # 检查Playwright管理的浏览器
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_path = compute_driver_executable()
        if driver_path and os.path.exists(str(driver_path)):
            # Playwright安装的浏览器在特定目录
            playwright_dir = os.path.dirname(os.path.dirname(str(driver_path)))
            for browser_type in BrowserType:
                browser_dir = os.path.join(playwright_dir, ".local-browsers", browser_type.value)
                if os.path.exists(browser_dir):
                    # 查找可执行文件
                    for root, dirs, files in os.walk(browser_dir):
                        for file in files:
                            if file.endswith(('.exe', '')) and browser_type.value in file.lower():
                                exe_path = os.path.join(root, file)
                                browsers.append(BrowserInfo(
                                    type=browser_type,
                                    executable_path=exe_path,
                                    is_playwright_managed=True
                                ))
    except (ImportError, Exception):
        pass
    
    # 检查系统安装的浏览器
    for browser_type, paths in default_paths.items():
        for path in paths:
            if os.path.exists(path):
                version = _get_browser_version(path)
                browsers.append(BrowserInfo(
                    type=browser_type,
                    executable_path=path,
                    version=version,
                    installed=True,
                    is_playwright_managed=False
                ))
                break  # 找到第一个即可
    
    # 检查PATH中的浏览器
    browser_commands = {
        "google-chrome": BrowserType.CHROME,
        "chrome": BrowserType.CHROME,
        "chromium": BrowserType.CHROMIUM,
        "chromium-browser": BrowserType.CHROMIUM,
        "firefox": BrowserType.FIREFOX
    }
    
    for cmd, browser_type in browser_commands.items():
        if _check_command_exists(cmd):
            exe_path = shutil.which(cmd)
            if exe_path and os.path.exists(exe_path):
                version = _get_browser_version(exe_path)
                browsers.append(BrowserInfo(
                    type=browser_type,
                    executable_path=exe_path,
                    version=version,
                    installed=True,
                    is_playwright_managed=False
                ))
    
    return browsers


def _validate_url(url: str) -> Tuple[bool, str]:
    """验证URL格式"""
    try:
        result = urlparse(url)
        if all([result.scheme, result.netloc]):
            return True, ""
        else:
            return False, "URL必须包含协议和域名"
    except Exception as e:
        return False, f"URL解析失败: {str(e)}"


def _validate_selector(selector: str) -> Tuple[bool, str]:
    """验证CSS选择器"""
    if not selector or not isinstance(selector, str):
        return False, "选择器不能为空且必须是字符串"
    
    # 基本验证
    if len(selector) > 1000:
        return False, "选择器过长"
    
    # 检查危险字符
    dangerous_patterns = ["javascript:", "data:", "vbscript:"]
    for pattern in dangerous_patterns:
        if pattern in selector.lower():
            return False, f"选择器包含危险内容: {pattern}"
    
    return True, ""


def _format_error_result(error: Exception, context: str = "") -> Dict[str, Any]:
    """格式化错误结果"""
    error_msg = str(error)
    
    # 常见错误类型映射
    error_mapping = {
        "timeout": "操作超时",
        "not found": "元素未找到",
        "network": "网络错误",
        "permission": "权限错误",
        "protocol": "协议错误"
    }
    
    error_type = "unknown"
    for key, value in error_mapping.items():
        if key in error_msg.lower():
            error_type = key
            break
    
    return {
        "success": False,
        "error": error_msg,
        "error_type": error_type,
        "context": context,
        "platform": _get_platform().value,
        "timestamp": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    }


async def _wait_for_page_ready(page, wait_for: Optional[Dict] = None):
    """现代的页面等待方式"""
    # 基础等待：DOM 加载完成
    await page.wait_for_load_state("domcontentloaded")
    
    # 如果没有特殊等待条件，等待少量静态资源
    if not wait_for:
        await page.wait_for_timeout(500)
        return
    
    # 处理等待条件
    if "selector" in wait_for:
        await page.wait_for_selector(wait_for["selector"], timeout=wait_for.get("timeout", 30000))
    elif "network" in wait_for:
        network_type = wait_for["network"]
        if network_type == "idle":
            # 使用 fetchidle 代替已废弃的 networkidle
            await page.wait_for_load_state("networkidle")
        elif network_type == "load":
            await page.wait_for_load_state("load")
    elif "function" in wait_for:
        # 等待 JS 条件满足
        await page.wait_for_function(wait_for["function"], timeout=wait_for.get("timeout", 30000))


def _get_browser_config(platform_type: Optional[PlatformType] = None) -> Dict[str, Any]:
    """获取浏览器配置，根据平台自动调整"""
    if platform_type is None:
        platform_type = _get_platform()
    
    # 平台特定的用户代理
    user_agents = {
        PlatformType.MACOS: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        PlatformType.WINDOWS: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        PlatformType.LINUX: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    return {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": user_agents.get(platform_type, user_agents[PlatformType.MACOS]),
        "ignore_https_errors": True,  # 忽略HTTPS证书错误
        "java_script_enabled": True,
        "bypass_csp": False,  # 谨慎使用
        "locale": "zh-CN" if platform_type == PlatformType.WINDOWS else "en-US"
    }


async def _launch_browser_with_fallback(p, browser_type: BrowserType = BrowserType.CHROMIUM, 
                                        headless: bool = True, 
                                        context_config: Optional[Dict] = None) -> Tuple[Any, Any, Any]:
    """
    统一的浏览器启动函数，支持多种浏览器和回退机制
    
    Args:
        p: Playwright实例
        browser_type: 首选浏览器类型
        headless: 是否无头模式
        context_config: 上下文配置
    
    Returns:
        (browser, context, page) 三元组
    
    Raises:
        RuntimeError: 所有浏览器启动尝试都失败
    """
    detected_browsers = _detect_installed_browsers()
    logger.info(f"检测到 {len(detected_browsers)} 个可用浏览器")
    
    # 按优先级排序：首选类型 > Playwright管理 > 系统安装
    browser_priority = [
        (browser_type, True, True),   # 首选类型，Playwright管理
        (browser_type, False, True),  # 首选类型，系统安装
        (BrowserType.CHROMIUM, True, True),  # Chromium，Playwright管理
        (BrowserType.CHROME, True, True),    # Chrome，Playwright管理
        (BrowserType.CHROMIUM, False, True), # Chromium，系统安装
        (BrowserType.CHROME, False, True),   # Chrome，系统安装
        (BrowserType.FIREFOX, True, True),   # Firefox，Playwright管理
        (BrowserType.WEBKIT, True, True),    # WebKit，Playwright管理
    ]
    
    launch_errors = []
    
    for target_type, prefer_playwright, _ in browser_priority:
        # 筛选匹配的浏览器
        matching_browsers = [
            b for b in detected_browsers 
            if b.type == target_type and b.is_playwright_managed == prefer_playwright
        ]
        
        for browser_info in matching_browsers:
            try:
                logger.info(f"尝试启动 {target_type.value} 浏览器 (Playwright管理: {prefer_playwright})")
                
                # 根据浏览器类型选择启动方法
                if target_type == BrowserType.CHROMIUM:
                    browser = await p.chromium.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox" if _get_platform() == PlatformType.LINUX else ""
                        ]
                    )
                elif target_type == BrowserType.CHROME:
                    browser = await p.chromium.launch(
                        headless=headless,
                        channel="chrome",
                        executable_path=browser_info.executable_path if not prefer_playwright else None,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox" if _get_platform() == PlatformType.LINUX else ""
                        ]
                    )
                elif target_type == BrowserType.FIREFOX:
                    browser = await p.firefox.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None
                    )
                elif target_type == BrowserType.WEBKIT:
                    browser = await p.webkit.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None
                    )
                else:
                    continue
                
                # 创建上下文和页面
                config = context_config or _get_browser_config()
                context = await browser.new_context(**config)
                page = await context.new_page()
                
                logger.info(f"成功启动 {target_type.value} 浏览器")
                return browser, context, page
                
            except Exception as e:
                error_msg = f"启动 {target_type.value} 失败: {str(e)}"
                launch_errors.append(error_msg)
                logger.warning(error_msg)
                continue
    
    # 如果所有尝试都失败，尝试使用Playwright的默认安装
    try:
        logger.info("尝试使用Playwright默认安装")
        browser = await p.chromium.launch(headless=headless)
        config = context_config or _get_browser_config()
        context = await browser.new_context(**config)
        page = await context.new_page()
        logger.info("成功使用Playwright默认安装启动浏览器")
        return browser, context, page
    except Exception as e:
        launch_errors.append(f"Playwright默认安装失败: {str(e)}")
    
    # 生成详细的错误信息
    error_details = "\n".join(launch_errors)
    platform_info = _get_platform().value
    browsers_found = [f"{b.type.value} ({'Playwright' if b.is_playwright_managed else '系统'})" 
                     for b in detected_browsers]
    
    raise RuntimeError(
        f"无法启动任何浏览器。\n"
        f"平台: {platform_info}\n"
        f"检测到的浏览器: {', '.join(browsers_found) if browsers_found else '无'}\n"
        f"错误详情:\n{error_details}\n"
        f"请运行以下命令安装浏览器:\n"
        f"  pip install playwright\n"
        f"  playwright install chromium chrome firefox"
    )


async def _launch_browser(p, headless: bool = True, context_config: Optional[Dict] = None):
    """向后兼容的浏览器启动函数"""
    return await _launch_browser_with_fallback(p, BrowserType.CHROMIUM, headless, context_config)


async def browser_automation(
    url: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    wait_for: Optional[Dict[str, Any]] = None,
    extract: Optional[List[str]] = None,
    screenshot: Optional[Dict[str, Any]] = None,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    retry_delay: float = 1.0
) -> Dict[str, Any]:
    """
    浏览器自动化操作 - 支持动态网页处理和数据提取
    
    Args:
        url: 目标URL
        actions: 操作列表，每项包含:
            - type: 操作类型 (click, input, select, hover, scroll, wait, evaluate, goto, back, forward)
            - selector: CSS选择器
            - value: 输入值/选项值
            - options: 额外选项
        wait_for: 等待条件
            - selector: 等待元素出现
            - network: 等待网络空闲 (idle, load)
            - function: JS函数条件
            - timeout: 超时时间(毫秒)
        extract: 提取数据类型列表
            - text: 文本内容
            - html: HTML内容
            - links: 链接列表
            - images: 图片列表
            - table: 表格数据
            - title: 页面标题
            - metadata: 元数据
            - all: 所有可提取内容
        screenshot: 截图配置
            - path: 保存路径
            - full_page: 是否截取整页
            - selector: 指定元素截图
        timeout: 超时时间(毫秒)，默认30000
        headless: 是否无头模式，默认True
        browser_type: 浏览器类型 (chromium, chrome, firefox, webkit)，默认chromium
        retry_count: 重试次数，默认2
        retry_delay: 重试延迟(秒)，默认1.0
    
    Returns:
        操作结果，包含:
            - success: 是否成功
            - url: 目标URL
            - title: 页面标题
            - actions_performed: 执行的操作列表
            - extracted_data: 提取的数据
            - screenshot: 截图信息
            - browser_info: 浏览器信息
            - platform: 操作系统平台
            - duration: 执行时长(秒)
            - error: 错误信息(如果失败)
            - error_type: 错误类型
            - retry_attempts: 重试次数
    """
    start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    logger.info(f"browser_automation 开始执行: {url}")
    
    # 参数验证
    validation_errors = []
    
    # 验证URL
    url_valid, url_error = _validate_url(url)
    if not url_valid:
        validation_errors.append(f"URL验证失败: {url_error}")
    
    # 验证actions
    if actions:
        if not isinstance(actions, list):
            validation_errors.append("actions必须是列表")
        else:
            for i, action in enumerate(actions):
                if not isinstance(action, dict):
                    validation_errors.append(f"action[{i}]必须是字典")
                elif "type" not in action:
                    validation_errors.append(f"action[{i}]缺少type字段")
                elif action.get("selector"):
                    selector_valid, selector_error = _validate_selector(action["selector"])
                    if not selector_valid:
                        validation_errors.append(f"action[{i}]选择器无效: {selector_error}")
    
    # 验证extract
    if extract:
        if not isinstance(extract, list):
            validation_errors.append("extract必须是列表")
        else:
            valid_extract_types = {"text", "html", "links", "images", "table", "title", "metadata", "all"}
            for extract_type in extract:
                if extract_type not in valid_extract_types:
                    validation_errors.append(f"不支持的extract类型: {extract_type}")
    
    # 验证timeout
    if not isinstance(timeout, int) or timeout < 1000 or timeout > 300000:
        validation_errors.append("timeout必须在1000-300000毫秒之间")
    
    # 验证browser_type
    valid_browser_types = {"chromium", "chrome", "firefox", "webkit"}
    if browser_type.lower() not in valid_browser_types:
        validation_errors.append(f"不支持的browser_type: {browser_type}")
    
    if validation_errors:
        return {
            "success": False,
            "url": url,
            "error": "参数验证失败",
            "validation_errors": validation_errors,
            "platform": _get_platform().value
        }
    
    # 转换browser_type
    browser_type_enum = BrowserType(browser_type.lower())
    
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return {
            "success": False,
            "url": url,
            "error": "Playwright未安装",
            "error_type": "import_error",
            "platform": _get_platform().value,
            "solution": "请运行: pip install playwright && playwright install chromium chrome firefox"
        }
    
    result = {
        "success": True,
        "url": url,
        "title": "",
        "actions_performed": [],
        "extracted_data": {},
        "screenshot": None,
        "browser_info": {
            "type": browser_type,
            "headless": headless,
            "platform": _get_platform().value
        },
        "platform": _get_platform().value,
        "duration": 0,
        "error": None,
        "error_type": None,
        "retry_attempts": 0
    }
    
    browser = None
    context = None
    page = None
    retry_attempts = 0
    
    for attempt in range(retry_count + 1):
        retry_attempts = attempt
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser, context, page = await _launch_browser_with_fallback(
                    p, 
                    browser_type=browser_type_enum, 
                    headless=headless
                )
                
                # 记录浏览器信息
                detected_browsers = _detect_installed_browsers()
                matching_browsers = [b for b in detected_browsers if b.type == browser_type_enum]
                if matching_browsers:
                    result["browser_info"]["detected_version"] = matching_browsers[0].version
                    result["browser_info"]["is_playwright_managed"] = matching_browsers[0].is_playwright_managed
                
                # 设置超时
                page.set_default_timeout(timeout)
                page.set_default_navigation_timeout(timeout)
                
                # 导航到URL
                navigation_start = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
                await page.goto(url, wait_until="domcontentloaded")
                navigation_end = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
                
                logger.info(f"已导航到: {url}")
                result["actions_performed"].append({
                    "type": "goto", 
                    "url": url,
                    "duration": navigation_end - navigation_start if navigation_end > navigation_start else 0
                })
                
                # 获取页面标题
                result["title"] = await page.title()
                
                # 执行预加载等待
                if wait_for:
                    await _wait_for_page_ready(page, wait_for)
                
                # 执行操作列表
                if actions:
                    for action in actions:
                        action_start = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
                        action_result = await _execute_action(page, action)
                        action_end = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
                        action_result["duration"] = action_end - action_start if action_end > action_start else 0
                        result["actions_performed"].append(action_result)
                
                # 等待页面稳定
                await page.wait_for_load_state("load")
                
                # 提取数据
                if extract:
                    for extract_type in extract:
                        data = await _extract_data(page, extract_type)
                        result["extracted_data"][extract_type] = data
                
                # 截图
                if screenshot:
                    screenshot_path = screenshot.get("path", "screenshot.png")
                    full_page = screenshot.get("full_page", False)
                    selector = screenshot.get("selector")
                    
                    # 确保目录存在
                    os.makedirs(os.path.dirname(screenshot_path) or ".", exist_ok=True)
                    
                    if selector:
                        element = await page.query_selector(selector)
                        if element:
                            await element.screenshot(path=screenshot_path)
                        else:
                            logger.warning(f"截图元素未找到: {selector}")
                            await page.screenshot(path=screenshot_path, full_page=full_page)
                    else:
                        await page.screenshot(path=screenshot_path, full_page=full_page)
                    
                    result["screenshot"] = {
                        "path": screenshot_path,
                        "full_page": full_page,
                        "selector": selector,
                        "file_size": os.path.getsize(screenshot_path) if os.path.exists(screenshot_path) else 0
                    }
                    result["actions_performed"].append({"type": "screenshot", "path": screenshot_path})
                
                # 计算执行时长
                end_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
                result["duration"] = end_time - start_time if end_time > start_time else 0
                result["retry_attempts"] = retry_attempts
                
                await browser.close()
                return result
                
        except PlaywrightTimeoutError as e:
            error_result = _format_error_result(e, "操作超时")
            error_result.update({
                "url": url,
                "retry_attempts": retry_attempts,
                "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
            })
            
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试超时，{retry_delay}秒后重试")
                await asyncio.sleep(retry_delay)
                continue
            else:
                return error_result
                
        except Exception as e:
            error_result = _format_error_result(e, "浏览器自动化失败")
            error_result.update({
                "url": url,
                "retry_attempts": retry_attempts,
                "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
            })
            
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试失败，{retry_delay}秒后重试: {str(e)}")
                await asyncio.sleep(retry_delay)
                continue
            else:
                return error_result
                
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
    
    # 所有重试都失败
    return {
        "success": False,
        "url": url,
        "error": f"所有 {retry_count + 1} 次尝试都失败",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_attempts,
        "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
    }


async def _handle_wait(page, wait_config: Dict[str, Any]):
    """处理等待条件"""
    if "selector" in wait_config:
        await page.wait_for_selector(wait_config["selector"], timeout=wait_config.get("timeout", 30000))
    elif "network" in wait_config:
        network_type = wait_config["network"]
        if network_type == "idle":
            await page.wait_for_load_state("networkidle")
        elif network_type == "slow":
            await page.wait_for_load_state("networkidle", timeout=60000)


async def _execute_action(page, action: Dict[str, Any]) -> Dict[str, Any]:
    """执行单个操作"""
    action_type = action.get("type", "")
    selector = action.get("selector", "")
    value = action.get("value", "")
    options = action.get("options", {})
    
    result = {"type": action_type, "selector": selector}
    
    try:
        if action_type == "click":
            await page.click(selector, **options)
            result["status"] = "success"
            
        elif action_type == "input":
            await page.fill(selector, str(value), **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "type":
            await page.type(selector, str(value), **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "select":
            await page.select_option(selector, value, **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "hover":
            await page.hover(selector, **options)
            result["status"] = "success"
            
        elif action_type == "scroll":
            if selector:
                await page.locator(selector).scroll_into_view_if_needed(**options)
            else:
                await page.evaluate(f"window.scrollBy(0, {value or 500})")
            result["status"] = "success"
            
        elif action_type == "wait":
            await page.wait_for_timeout(int(value) if value else 1000)
            result["status"] = "success"
            
        elif action_type == "evaluate":
            js_result = await page.evaluate(value)
            result["status"] = "success"
            result["result"] = js_result
            
        elif action_type == "goto":
            await page.goto(value, wait_until="domcontentloaded")
            result["status"] = "success"
            
        elif action_type == "back":
            await page.go_back()
            result["status"] = "success"
            
        elif action_type == "forward":
            await page.go_forward()
            result["status"] = "success"
            
        else:
            result["status"] = "unknown_action"
            
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


async def _extract_data(page, extract_type: str) -> Any:
    """提取页面数据"""
    try:
        if extract_type == "text":
            return await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText.trim() : '';
                }
            """)
            
        elif extract_type == "html":
            return await page.content()
            
        elif extract_type == "links":
            return await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links.map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    })).filter(l => l.href);
                }
            """)
            
        elif extract_type == "images":
            return await page.evaluate("""
                () => {
                    const imgs = Array.from(document.querySelectorAll('img[src]'));
                    return imgs.map(img => ({
                        src: img.src,
                        alt: img.alt || ''
                    })).filter(i => i.src);
                }
            """)
            
        elif extract_type == "table":
            return await page.evaluate("""
                () => {
                    const tables = Array.from(document.querySelectorAll('table'));
                    return tables.map(table => {
                        const rows = Array.from(table.querySelectorAll('tr'));
                        return rows.map(row => {
                            const cells = Array.from(row.querySelectorAll('th, td'));
                            return cells.map(cell => cell.innerText.trim());
                        });
                    });
                }
            """)
            
        elif extract_type == "title":
            return await page.title()
            
        elif extract_type == "metadata":
            return await page.evaluate("""
                () => {
                    const meta = {};
                    document.querySelectorAll('meta').forEach(m => {
                        if (m.name) meta[m.name] = m.content;
                        if (m.getAttribute('property')) meta[m.getAttribute('property')] = m.content;
                    });
                    return meta;
                }
            """)
            
        elif extract_type == "all":
            return {
                "title": await page.title(),
                "text": await _extract_data(page, "text"),
                "links": await _extract_data(page, "links"),
                "images": await _extract_data(page, "images"),
                "metadata": await _extract_data(page, "metadata")
            }
            
    except Exception as e:
        return {"error": str(e)}
    
    return None


async def scrape_dynamic_page(
    url: str,
    selectors: Optional[List[str]] = None,
    wait_for_selector: Optional[str] = None,
    extract_text: bool = True,
    extract_links: bool = False,
    extract_tables: bool = False,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2
) -> Dict[str, Any]:
    """
    抓取动态网页内容 - 适用于JavaScript渲染的页面
    
    Args:
        url: 目标URL
        selectors: CSS选择器列表，指定要提取的元素
        wait_for_selector: 等待元素出现后再提取
        extract_text: 是否提取文本
        extract_links: 是否提取链接
        extract_tables: 是否提取表格
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数
    
    Returns:
        抓取结果
    """
    start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    logger.info(f"scrape_dynamic_page 开始执行: {url}")
    
    # 参数验证
    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {
            "success": False,
            "url": url,
            "error": f"URL验证失败: {url_error}",
            "platform": _get_platform().value
        }
    
    if selectors:
        for i, selector in enumerate(selectors):
            selector_valid, selector_error = _validate_selector(selector)
            if not selector_valid:
                return {
                    "success": False,
                    "url": url,
                    "error": f"选择器[{i}]无效: {selector_error}",
                    "platform": _get_platform().value
                }
    
    if wait_for_selector:
        selector_valid, selector_error = _validate_selector(wait_for_selector)
        if not selector_valid:
            return {
                "success": False,
                "url": url,
                "error": f"等待选择器无效: {selector_error}",
                "platform": _get_platform().value
            }
    
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return {
            "success": False,
            "url": url,
            "error": "Playwright未安装",
            "error_type": "import_error",
            "platform": _get_platform().value
        }
    
    result = {
        "success": True,
        "url": url,
        "title": "",
        "content": {},
        "platform": _get_platform().value,
        "duration": 0,
        "error": None,
        "retry_attempts": 0
    }
    
    browser_type_enum = BrowserType(browser_type.lower())
    
    for attempt in range(retry_count + 1):
        browser = None
        try:
            async with async_playwright() as p:
                browser, context, page = await _launch_browser_with_fallback(
                    p, 
                    browser_type=browser_type_enum, 
                    headless=headless
                )
                
                page.set_default_timeout(timeout)
                page.set_default_navigation_timeout(timeout)
                
                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"已导航到: {url}")
                
                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)
                
                await page.wait_for_load_state("load")
                
                result["title"] = await page.title()
                
                if extract_text:
                    result["content"]["text"] = await page.evaluate(
                        "() => document.body.innerText.trim()"
                    )
                
                if extract_links:
                    result["content"]["links"] = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => ({text: a.innerText.trim(), href: a.href}))
                            .filter(l => l.href)
                    """)
                
                if extract_tables:
                    result["content"]["tables"] = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('table')).map(table => {
                            return Array.from(table.querySelectorAll('tr')).map(row => 
                                Array.from(row.querySelectorAll('th, td')).map(c => c.innerText.trim())
                            );
                        })
                    """)
                
                if selectors:
                    for sel in selectors:
                        safe_sel = sel.replace("'", "\\'").replace('"', '\\"')
                        result["content"][f"selector_{sel}"] = await page.evaluate(f"""
                            () => {{
                                try {{
                                    const els = document.querySelectorAll('{safe_sel}');
                                    return Array.from(els).map(el => {{
                                        return {{
                                            text: el.innerText.trim(),
                                            html: el.innerHTML,
                                            tag: el.tagName.toLowerCase(),
                                            id: el.id || '',
                                            class: el.className || ''
                                        }};
                                    }});
                                }} catch (e) {{
                                    return {{error: e.toString()}};
                                }}
                            }}
                        """)
                
                result["retry_attempts"] = attempt
                result["duration"] = (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                
                await browser.close()
                return result
                
        except PlaywrightTimeoutError as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试超时，1秒后重试")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "抓取超时")
                error_result.update({
                    "url": url,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试失败，1秒后重试: {str(e)}")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "抓取失败")
                error_result.update({
                    "url": url,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
    
    return {
        "success": False,
        "url": url,
        "error": f"所有 {retry_count + 1} 次尝试都失败",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
    }


async def take_screenshot(
    url: str,
    output_path: str = "screenshot.png",
    selector: Optional[str] = None,
    full_page: bool = False,
    wait_for_selector: Optional[str] = None,
    delay: int = 0,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    viewport_width: int = 1920,
    viewport_height: int = 1080
) -> Dict[str, Any]:
    """
    页面截图 - 支持整页截图和元素截图
    
    Args:
        url: 目标URL
        output_path: 截图保存路径
        selector: 指定元素截图(为空则截取整个视口)
        full_page: 是否截取整页
        wait_for_selector: 等待元素出现后再截图
        delay: 加载后延迟时间(毫秒)
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数
        viewport_width: 视口宽度
        viewport_height: 视口高度
    
    Returns:
        截图结果
    """
    start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    logger.info(f"take_screenshot 开始执行: {url}")
    
    # 参数验证
    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {
            "success": False,
            "url": url,
            "screenshot_path": output_path,
            "error": f"URL验证失败: {url_error}",
            "platform": _get_platform().value
        }
    
    if selector:
        selector_valid, selector_error = _validate_selector(selector)
        if not selector_valid:
            return {
                "success": False,
                "url": url,
                "screenshot_path": output_path,
                "error": f"选择器无效: {selector_error}",
                "platform": _get_platform().value
            }
    
    if wait_for_selector:
        selector_valid, selector_error = _validate_selector(wait_for_selector)
        if not selector_valid:
            return {
                "success": False,
                "url": url,
                "screenshot_path": output_path,
                "error": f"等待选择器无效: {selector_error}",
                "platform": _get_platform().value
            }
    
    if delay < 0 or delay > 30000:
        return {
            "success": False,
            "url": url,
            "screenshot_path": output_path,
            "error": "delay必须在0-30000毫秒之间",
            "platform": _get_platform().value
        }
    
    if viewport_width < 100 or viewport_width > 5000 or viewport_height < 100 or viewport_height > 5000:
        return {
            "success": False,
            "url": url,
            "screenshot_path": output_path,
            "error": "视口尺寸必须在100-5000像素之间",
            "platform": _get_platform().value
        }
    
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return {
            "success": False,
            "url": url,
            "screenshot_path": output_path,
            "error": "Playwright未安装",
            "error_type": "import_error",
            "platform": _get_platform().value
        }
    
    result = {
        "success": True,
        "url": url,
        "screenshot_path": output_path,
        "selector": selector,
        "full_page": full_page,
        "viewport": {"width": viewport_width, "height": viewport_height},
        "platform": _get_platform().value,
        "duration": 0,
        "error": None,
        "retry_attempts": 0
    }
    
    browser_type_enum = BrowserType(browser_type.lower())
    
    for attempt in range(retry_count + 1):
        browser = None
        try:
            async with async_playwright() as p:
                browser, context, page = await _launch_browser_with_fallback(
                    p, 
                    browser_type=browser_type_enum, 
                    headless=headless
                )
                
                # 设置视口
                await context.set_viewport_size({"width": viewport_width, "height": viewport_height})
                page.set_default_timeout(timeout)
                page.set_default_navigation_timeout(timeout)
                
                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"已导航到: {url}")
                
                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)
                
                if delay > 0:
                    await page.wait_for_timeout(delay)
                
                await page.wait_for_load_state("load")
                
                # 确保目录存在
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                
                if selector:
                    element = await page.query_selector(selector)
                    if element:
                        await element.screenshot(path=output_path)
                        result["element_found"] = True
                        
                        # 获取元素信息
                        element_info = await page.evaluate("""(el) => {
                            const rect = el.getBoundingClientRect();
                            return {
                                tag: el.tagName.toLowerCase(),
                                visible: el.offsetParent !== null,
                                position: {
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height)
                                }
                            };
                        }""", element)
                        result["element_info"] = element_info
                    else:
                        result["success"] = False
                        result["error"] = f"未找到元素: {selector}"
                        result["element_found"] = False
                else:
                    await page.screenshot(path=output_path, full_page=full_page)
                
                if os.path.exists(output_path):
                    result["file_size"] = os.path.getsize(output_path)
                    result["file_exists"] = True
                else:
                    result["file_exists"] = False
                    result["success"] = False
                    result["error"] = "截图文件未生成"
                
                result["retry_attempts"] = attempt
                result["duration"] = (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                
                await browser.close()
                return result
                
        except PlaywrightTimeoutError as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试超时，1秒后重试")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "截图超时")
                error_result.update({
                    "url": url,
                    "screenshot_path": output_path,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试失败，1秒后重试: {str(e)}")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "截图失败")
                error_result.update({
                    "url": url,
                    "screenshot_path": output_path,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
    
    return {
        "success": False,
        "url": url,
        "screenshot_path": output_path,
        "error": f"所有 {retry_count + 1} 次尝试都失败",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
    }


async def test_element_exists(
    url: str,
    selector: str,
    wait_for_selector: Optional[str] = None,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    check_visibility: bool = True
) -> Dict[str, Any]:
    """
    测试页面元素是否存在 - 用于前端测试
    
    Args:
        url: 目标URL
        selector: CSS选择器
        wait_for_selector: 等待元素出现
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数
        check_visibility: 是否检查元素可见性
    
    Returns:
        测试结果
    """
    start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    logger.info(f"test_element_exists 开始执行: {url}, selector: {selector}")
    
    # 参数验证
    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {
            "success": False,
            "url": url,
            "selector": selector,
            "exists": False,
            "error": f"URL验证失败: {url_error}",
            "platform": _get_platform().value
        }
    
    selector_valid, selector_error = _validate_selector(selector)
    if not selector_valid:
        return {
            "success": False,
            "url": url,
            "selector": selector,
            "exists": False,
            "error": f"选择器无效: {selector_error}",
            "platform": _get_platform().value
        }
    
    if wait_for_selector:
        selector_valid, selector_error = _validate_selector(wait_for_selector)
        if not selector_valid:
            return {
                "success": False,
                "url": url,
                "selector": selector,
                "exists": False,
                "error": f"等待选择器无效: {selector_error}",
                "platform": _get_platform().value
            }
    
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return {
            "success": False,
            "url": url,
            "selector": selector,
            "exists": False,
            "error": "Playwright未安装",
            "error_type": "import_error",
            "platform": _get_platform().value
        }
    
    result = {
        "success": True,
        "url": url,
        "selector": selector,
        "exists": False,
        "visible": False,
        "count": 0,
        "platform": _get_platform().value,
        "duration": 0,
        "error": None,
        "retry_attempts": 0
    }
    
    browser_type_enum = BrowserType(browser_type.lower())
    
    for attempt in range(retry_count + 1):
        browser = None
        try:
            async with async_playwright() as p:
                browser, context, page = await _launch_browser_with_fallback(
                    p, 
                    browser_type=browser_type_enum, 
                    headless=headless
                )
                
                page.set_default_timeout(timeout)
                page.set_default_navigation_timeout(timeout)
                
                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"已导航到: {url}")
                
                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)
                
                await page.wait_for_load_state("load")
                
                # 检查元素存在性和数量
                elements = await page.query_selector_all(selector)
                result["count"] = len(elements)
                result["exists"] = len(elements) > 0
                
                if elements:
                    # 获取第一个元素的信息
                    first_element = elements[0]
                    element_info = await page.evaluate("""(el, checkVisibility) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const attributes = {};
                        for (const attr of el.attributes) {
                            attributes[attr.name] = attr.value;
                        }
                        
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText.trim().substring(0, 200),
                            visible: checkVisibility ? (el.offsetParent !== null && 
                                     style.display !== 'none' && 
                                     style.visibility !== 'hidden' &&
                                     rect.width > 0 && rect.height > 0) : true,
                            position: {
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            },
                            style: {
                                display: style.display,
                                visibility: style.visibility,
                                opacity: style.opacity
                            },
                            attributes: attributes,
                            classes: el.className.split(' ').filter(c => c.trim()),
                            id: el.id || ''
                        };
                    }""", first_element, check_visibility)
                    
                    result["element_info"] = element_info
                    result["visible"] = element_info["visible"]
                    
                    # 获取所有匹配元素的基本信息
                    if len(elements) > 1:
                        result["all_elements"] = []
                        for i, element in enumerate(elements[:10]):  # 限制前10个
                            basic_info = await page.evaluate("""(el) => {
                                const rect = el.getBoundingClientRect();
                                return {
                                    tag: el.tagName.toLowerCase(),
                                    text: el.innerText.trim().substring(0, 50),
                                    position: {
                                        x: Math.round(rect.x),
                                        y: Math.round(rect.y)
                                    }
                                };
                            }""", element)
                            result["all_elements"].append(basic_info)
                
                result["retry_attempts"] = attempt
                result["duration"] = (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                
                await browser.close()
                return result
                
        except PlaywrightTimeoutError as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试超时，1秒后重试")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "元素测试超时")
                error_result.update({
                    "url": url,
                    "selector": selector,
                    "exists": False,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"第 {attempt + 1} 次尝试失败，1秒后重试: {str(e)}")
                await asyncio.sleep(1)
                continue
            else:
                error_result = _format_error_result(e, "元素测试失败")
                error_result.update({
                    "url": url,
                    "selector": selector,
                    "exists": False,
                    "retry_attempts": attempt,
                    "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
                })
                return error_result
                
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
    
    return {
        "success": False,
        "url": url,
        "selector": selector,
        "exists": False,
        "error": f"所有 {retry_count + 1} 次尝试都失败",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": (asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0) - start_time
    }


async def _get_system_browser_info() -> Dict[str, Any]:
    """
    获取系统浏览器信息 - 用于诊断和调试
    
    Returns:
        浏览器信息
    """
    platform_type = _get_platform()
    browsers = _detect_installed_browsers()
    
    return {
        "platform": platform_type.value,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "python_version": sys.version,
        "detected_browsers": [
            {
                "type": b.type.value,
                "executable_path": b.executable_path,
                "version": b.version,
                "installed": b.installed,
                "is_playwright_managed": b.is_playwright_managed
            }
            for b in browsers
        ],
        "default_paths": {
            browser_type.value: paths
            for browser_type, paths in _get_default_browser_paths().items()
            if paths
        },
        "timestamp": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    }


async def _check_playwright_installation() -> Dict[str, Any]:
    """
    检查Playwright安装状态
    
    Returns:
        安装状态信息
    """
    result = {
        "playwright_installed": False,
        "browsers_installed": [],
        "platform": _get_platform().value,
        "errors": []
    }
    
    # 检查Playwright包
    try:
        from playwright._repo_version import version as playwright_version
        result["playwright_installed"] = True
        result["playwright_version"] = playwright_version
    except ImportError:
        # 尝试其他方式
        try:
            import playwright
            result["playwright_installed"] = True
            result["playwright_version"] = "未知(已安装)"
        except ImportError:
            result["errors"].append("Playwright包未安装")
            return result
    
    # 检查浏览器
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_path = compute_driver_executable()
        if driver_path:
            result["driver_path"] = str(driver_path)
            
            # 检查Playwright管理的浏览器
            playwright_dir = os.path.dirname(os.path.dirname(str(driver_path)))
            browsers_dir = os.path.join(playwright_dir, ".local-browsers")
            
            if os.path.exists(browsers_dir):
                for browser_type in BrowserType:
                    browser_path = os.path.join(browsers_dir, browser_type.value)
                    if os.path.exists(browser_path):
                        result["browsers_installed"].append(browser_type.value)
    except Exception as e:
        result["errors"].append(f"检查浏览器时出错: {str(e)}")
    
    # 检查系统浏览器
    system_browsers = _detect_installed_browsers()
    result["system_browsers"] = [
        {
            "type": b.type.value,
            "version": b.version,
            "is_playwright_managed": b.is_playwright_managed
        }
        for b in system_browsers
    ]
    
    return result


# 使用示例
async def _example_usage():
    """使用示例"""
    print("=== Playwright Skill 使用示例 ===")
    
    # 1. 检查系统信息
    print("\n1. 系统浏览器信息:")
    browser_info = await _get_system_browser_info()
    print(f"平台: {browser_info['platform']}")
    print(f"检测到的浏览器: {len(browser_info['detected_browsers'])} 个")
    
    # 2. 检查安装状态
    print("\n2. Playwright安装状态:")
    install_status = await _check_playwright_installation()
    print(f"Playwright已安装: {install_status['playwright_installed']}")
    if install_status['playwright_installed']:
        print(f"版本: {install_status.get('playwright_version', '未知')}")
        print(f"Playwright管理的浏览器: {', '.join(install_status['browsers_installed'])}")
    
    # 3. 测试简单操作
    print("\n3. 测试简单操作:")
    try:
        # 测试百度首页
        test_url = "https://www.baidu.com"
        print(f"测试URL: {test_url}")
        
        # 测试元素存在
        test_result = await test_element_exists(
            url=test_url,
            selector="#kw",
            timeout=10000,
            retry_count=1
        )
        
        if test_result["success"]:
            print(f"元素存在: {test_result['exists']}")
            if test_result["exists"]:
                print(f"元素数量: {test_result['count']}")
                print(f"元素可见: {test_result['visible']}")
        else:
            print(f"测试失败: {test_result['error']}")
            
    except Exception as e:
        print(f"示例执行出错: {str(e)}")
    
    print("\n=== 示例结束 ===")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(_example_usage())
