# API Client Skill

## 描述
HTTP API调用工具，支持GET/POST/PUT/DELETE请求。

## 调用示例：
Action: make_request
Action Input: {"method": "GET", "url": "https://api.github.com/repos/owner/repo"}

## 输入参数

- `method` (str, 必需): HTTP方法 [GET, POST, PUT, DELETE]
- `url` (str, 必需): 请求URL
- `headers` (dict, 可选): 请求头
- `data` (dict, 可选): 请求数据
- `params` (dict, 可选): URL参数
- `timeout` (int, 可选): 超时时间(秒)，默认30
- `retry_count` (int, 可选): 重试次数，默认3

## 输出
- `success`: 是否成功
- `status_code`: HTTP状态码
- `headers`: 响应头
- `body`: 响应体
