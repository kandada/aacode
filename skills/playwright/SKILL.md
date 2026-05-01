## Description
Browser automation tool using Playwright. Supports dynamic web pages, data extraction, frontend testing, screenshots.

## Parameters
- url: Target URL
- headless: Headless mode, default true
- browser_type: Browser type [chromium, firefox, webkit], default chromium
- timeout: Timeout (ms), default 30000
- retry_count: Retry count, default 2

## Example
run_skills("playwright", {"func": "browser_automation", "url": "https://example.com"})
run_skills("playwright", {"func": "take_screenshot", "url": "https://example.com", "output_path": "screenshot.png"})
run_skills("playwright", {"func": "scrape_dynamic_page", "url": "https://example.com"})
