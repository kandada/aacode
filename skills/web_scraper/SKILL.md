# Web Scraper Skill

## 描述
网页抓取和数据提取工具，提供网页内容抓取、HTML解析、数据提取、链接提取、表格提取、内容清洗等功能。支持单页和多页并发抓取。

## 适用场景
- 抓取网页数据进行分析
- 提取新闻/文章内容
- 收集产品信息
- 监控网站更新
- 数据采集任务
- 网页内容分析

## 输入参数

### 单页抓取 (scrape_web)
- `url` (必需): 目标URL
- `operations` (必需): 要执行的操作列表
  - `extract_text`: 提取文本内容
  - `extract_links`: 提取链接
  - `extract_images`: 提取图片
  - `extract_tables`: 提取表格数据
  - `extract_metadata`: 提取元数据
  - `clean_content`: 清理HTML内容
- `selector` (可选): CSS选择器（用于提取特定元素）
- `max_pages` (可选): 最大抓取页数（默认1）
- `timeout` (可选): 超时时间（秒，默认30）

### 多页并发抓取 (scrape_multiple)
- `urls` (必需): URL列表
- `operations` (必需): 要执行的操作列表
- `concurrency` (可选): 并发数（默认3）
- `timeout` (可选): 超时时间（秒，默认30）

## 输出

### 单页抓取返回结果
- `success`: 操作是否成功
- `url`: 目标URL
- `pages_scraped`: 抓取的页数
- `operations_performed`: 执行的操作列表
- `scraped_data`: 抓取的数据列表（每页一个）
  - `url`: 页面URL
  - `title`: 页面标题
  - `operations`: 操作结果列表
    - `name`: 操作名称
    - `data`: 操作数据
- `total_links_found`: 找到的总链接数
- `sample_links`: 示例链接（前10个）

### 多页抓取返回结果
- `success`: 操作是否成功
- `total_urls`: 总URL数
- `successful`: 成功抓取的URL数
- `failed`: 失败的URL数
- `results`: 成功结果列表
- `failed_urls`: 失败URL列表（前10个）

### 操作数据详情
- `extract_text`: `full_text`（完整文本）, `text_length`（文本长度）, `paragraphs`（段落列表）, `paragraph_count`（段落数）
- `extract_links`: `all_links`（所有链接）, `internal_links`（内部链接）, `external_links`（外部链接）, `total_count`（总数）
- `extract_images`: `images`（图片列表）, `total_count`（总数）
- `extract_tables`: `tables`（表格列表）, `total_count`（总数）
- `extract_metadata`: `meta_tags`（meta标签）, `og_data`（Open Graph数据）, `json_ld`（JSON-LD数据）
- `clean_content`: `cleaned_text`（清理后的文本）, `char_count`（字符数）, `sentence_count`（句子数）, `sentences`（句子列表）

## 使用示例

### 示例1: 提取网页文本和链接
```json
{
  "url": "https://example.com",
  "operations": ["extract_text", "extract_links"],
  "timeout": 20
}
```

### 示例2: 提取图片和元数据
```json
{
  "url": "https://news.example.com/article",
  "operations": ["extract_images", "extract_metadata"],
  "selector": ".article-content"
}
```

### 示例3: 提取表格数据
```json
{
  "url": "https://data.example.com/table",
  "operations": ["extract_tables", "clean_content"]
}
```

### 示例4: 并发抓取多个URL
```json
{
  "urls": ["https://site1.com", "https://site2.com", "https://site3.com"],
  "operations": ["extract_text", "extract_links"],
  "concurrency": 5,
  "timeout": 30
}
```