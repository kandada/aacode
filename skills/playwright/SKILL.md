# Playwright Browser Automation

## 描述
浏览器自动化工具，支持动态网页处理、数据提取、前端测试和截图功能。

## 主要功能

### browser_automation
浏览器自动化操作，支持点击、输入、滚动等交互。

### scrape_dynamic_page
抓取JavaScript渲染的页面内容。

### take_screenshot
页面截图，支持整页、元素和延迟截图。

### test_element_exists
检查页面元素是否存在和可见。

## 输入参数

### browser_automation
- `url` (str, 必需): 目标URL
- `actions` (List[Dict], 可选): 操作序列
- `wait_for` (Dict, 可选): 等待条件
- `extract` (List[str], 可选): 提取类型 [text, html, links, images, table, title, metadata, all]
- `screenshot` (Dict, 可选): 截图配置
- `timeout` (int, 可选): 超时时间(ms)，默认30000
- `headless` (bool, 可选): 无头模式，默认true
- `browser_type` (str, 可选): 浏览器类型 [chromium, chrome, firefox, webkit]，默认chromium
- `retry_count` (int, 可选): 重试次数，默认2
- `retry_delay` (float, 可选): 重试延迟(s)，默认1.0

### scrape_dynamic_page
- `url` (str, 必需): 目标URL
- `selectors` (List[str], 可选): CSS选择器列表
- `wait_for_selector` (str, 可选): 等待元素选择器
- `extract_text` (bool, 可选): 提取文本，默认true
- `extract_links` (bool, 可选): 提取链接，默认false
- `extract_tables` (bool, 可选): 提取表格，默认false
- `timeout` (int, 可选): 超时时间(ms)，默认30000
- `headless` (bool, 可选): 无头模式，默认true
- `browser_type` (str, 可选): 浏览器类型，默认chromium
- `retry_count` (int, 可选): 重试次数，默认2

### take_screenshot
- `url` (str, 必需): 目标URL
- `output_path` (str, 可选): 保存路径，默认"screenshot.png"
- `selector` (str, 可选): 元素选择器
- `full_page` (bool, 可选): 整页截图，默认false
- `wait_for_selector` (str, 可选): 等待元素选择器
- `delay` (int, 可选): 延迟时间(ms)，默认0
- `timeout` (int, 可选): 超时时间(ms)，默认30000
- `headless` (bool, 可选): 无头模式，默认true
- `browser_type` (str, 可选): 浏览器类型，默认chromium
- `retry_count` (int, 可选): 重试次数，默认2
- `viewport_width` (int, 可选): 视口宽度，默认1920
- `viewport_height` (int, 可选): 视口高度，默认1080

### test_element_exists
- `url` (str, 必需): 目标URL
- `selector` (str, 必需): 元素选择器
- `wait_for_selector` (str, 可选): 等待元素选择器
- `timeout` (int, 可选): 超时时间(ms)，默认30000
- `headless` (bool, 可选): 无头模式，默认true
- `browser_type` (str, 可选): 浏览器类型，默认chromium
- `retry_count` (int, 可选): 重试次数，默认2
- `check_visibility` (bool, 可选): 检查可见性，默认true

## 输出

### browser_automation
- `success` (bool): 是否成功
- `url` (str): 目标URL
- `title` (str): 页面标题
- `actions_performed` (List): 执行的操作
- `extracted_data` (Dict): 提取的数据
- `screenshot` (Dict): 截图信息
- `browser_info` (Dict): 浏览器信息
- `duration` (float): 执行时长(s)

### scrape_dynamic_page
- `success` (bool): 是否成功
- `url` (str): 目标URL
- `title` (str): 页面标题
- `content` (Dict): 提取的内容
- `duration` (float): 执行时长(s)

### take_screenshot
- `success` (bool): 是否成功
- `url` (str): 目标URL
- `screenshot_path` (str): 截图路径
- `file_size` (int): 文件大小(bytes)
- `duration` (float): 执行时长(s)

### test_element_exists
- `success` (bool): 是否成功
- `exists` (bool): 元素是否存在
- `element_info` (Dict): 元素详细信息
- `duration` (float): 执行时长(s)

## 使用示例

### browser_automation
```json
{
  "url": "https://www.baidu.com",
  "actions": [
    {"type": "input", "selector": "#kw", "value": "测试"},
    {"type": "click", "selector": "#su"}
  ],
  "extract": ["text", "links"],
  "timeout": 30000
}
```

### scrape_dynamic_page
```json
{
  "url": "https://example.com",
  "selectors": [".content", ".title"],
  "extract_text": true,
  "extract_links": true
}
```

### take_screenshot
```json
{
  "url": "https://example.com",
  "output_path": "screenshot.png",
  "full_page": true,
  "delay": 1000
}
```

### test_element_exists
```json
{
  "url": "https://example.com",
  "selector": ".login-button",
  "check_visibility": true
}
```

## 注意事项
1. 首次使用需安装: `pip install playwright && playwright install chromium`
2. 无头模式适合自动化，非无头模式可见浏览器界面
3. 动态页面建议设置足够timeout
4. 支持重试机制，默认重试2次
