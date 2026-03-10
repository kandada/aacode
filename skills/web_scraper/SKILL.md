# Web Scraper Skill

## 描述
网页抓取和数据提取工具，支持单页和多页并发抓取。

## 调用示例：
Action: scrape_web
Action Input: {"url": "https://example.com", "operations": ["extract_text", "extract_links"]}

## 输入参数

### scrape_web
- `url` (str, 必需): 目标URL
- `operations` (list, 必需): 操作列表 [extract_text, extract_links, extract_images, extract_tables, extract_metadata, clean_content]
- `selector` (str, 可选): CSS选择器
- `timeout` (int, 可选): 超时时间(秒)，默认30

### scrape_multiple
- `urls` (list, 必需): URL列表
- `operations` (list, 必需): 操作列表
- `concurrency` (int, 可选): 并发数，默认3

## 输出
- `success`: 是否成功
- `scraped_data`: 抓取的数据
- `total_links_found`: 链接数量
