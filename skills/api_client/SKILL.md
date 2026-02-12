# API Client Skill

## 描述
提供HTTP API调用能力，支持GET/POST/PUT/DELETE请求，自动处理JSON、认证、错误重试等。

## 适用场景
- 调用RESTful APIs
- 第三方服务集成
- Webhook发送
- API测试和调试

## 输入参数
- `method`: HTTP方法（GET, POST, PUT, DELETE）
- `url`: 请求URL
- `headers`: 请求头（可选）
- `data`: 请求数据（可选，用于POST/PUT）
- `params`: URL查询参数（可选）
- `timeout`: 超时时间秒数（默认30）
- `retry_count`: 重试次数（默认3）

## 输出
返回API响应（status_code, headers, body等）

## 使用示例
```json
{
  "method": "GET",
  "url": "https://api.github.com/repos/{owner}/{repo}",
  "headers": {"Authorization": "Bearer token123"}
}
```
