## Context

当前页面抓取使用 `httpx.Client`。在用户环境中，CSDN 连接出现 TLS `UNEXPECTED_EOF_WHILE_READING`，而 Windows 系统 HTTPS 请求能够获取相同页面。修复应保持抓取结果模型不变，只替换传输层。

## Goals / Non-Goals

**Goals:**

- 让公开 CSDN 页面在当前 Windows 环境下使用更兼容的 TLS 传输方式。
- 保持最终 URL、状态码、响应正文和可读错误信息的现有接口。
- 让测试不依赖外网，通过模拟标准库响应覆盖主要错误路径。

**Non-Goals:**

- 不绕过登录、付费、验证码或其他访问控制。
- 不改变资源下载、正文提取或输出格式流程。

## Decisions

- 使用 `urllib.request.Request` 和 `urlopen` 获取页面；它使用 Python/Windows 标准 TLS 栈，已验证可访问用户提供的 CSDN 地址。
- 请求头使用 Chrome 风格的 User-Agent、Accept、Accept-Language 和 Upgrade-Insecure-Requests；urllib 默认跟随 HTTP 重定向。
- 将 HTTPError、URLError、SSL 错误和 OSError 转换为当前 `FetchError`，保留 HTTP 状态码或底层错误原因。
- 根据响应头 charset 解码正文，缺失或异常编码时回退 UTF-8 并替换非法字节，避免因编码问题丢失整页。

## Risks / Trade-offs

- **不同平台的系统 TLS 行为不同** → 使用标准库接口而不是 Windows 专属 API，并保留明确的连接错误信息。
- **WAF 仍可能临时返回 521** → 不伪造成功；保留具体 HTTP 状态，后续可单独增加重试策略。

## Migration Plan

无需数据迁移。重启 Web 服务后，新的文章请求会使用兼容抓取方式；已有归档文件不受影响。
