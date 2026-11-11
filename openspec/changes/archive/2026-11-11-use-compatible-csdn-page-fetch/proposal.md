## Why

部分 CSDN 请求在 `httpx` TLS 握手阶段被服务端提前断开，Web 页面因此显示 `SSL: UNEXPECTED_EOF_WHILE_READING`，即使同一地址可以通过系统 HTTPS 请求正常访问。需要替换页面抓取传输方式，提升公开文章导入的兼容性。

## What Changes

- 使用 Python 标准库 HTTPS 请求抓取文章页面，保留重定向、状态码、编码和错误处理。
- 使用接近真实浏览器的请求头，减少被 CSDN WAF 误判的概率。
- 保留现有 CSDN 域名校验、登录/付费判断和正文解析流程。
- 增加连接成功、HTTP 错误和 TLS/连接异常的回归测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。现有归档规格已经要求支持公开文章；本变更只替换页面抓取实现以满足既有行为。

## Impact

- 修改 `app/fetcher.py` 的页面网络请求实现和错误映射。
- 不改变 Web API、归档结构、HTML/PDF 输出或搜索行为。
