# csdn 单个连接下载

将一个公开 CSDN 文章连接保存为本地 HTML、PDF 或两者，保留正文、图片、代码和必要排版，降低文章因网站停止运营或内容下线而丢失的风险。

## 功能

- Web 服务提交单个公开 CSDN 文章 URL
- 默认保存 HTML，可选择 PDF 或 HTML+PDF
- 只提取正文及正文资源，不保存评论、广告和侧边栏
- 保留代码注释、换行、缩进、空白和边框字符
- 代码块默认折叠，打印和 PDF 中保持可见
- 文件保存到 `data/`，同一 URL 重复下载时覆盖旧版本
- 首页显示已下载文件列表，并支持按标题、域名、URL、作者和标签搜索
- 支持输入 CSDN 专题地址，按顺序批量下载并生成带导航的 HTML、EPUB 或 PDF（单选）
- 专题下载支持调整并行数量，默认值为 1，并保留专题文章顺序
- 提交专题后，可在进度页查看处理阶段、篇数和耗时，结束后在同一页面查看结果
- 专题文章请求会携带现代浏览器导航头和专题页 Referer，降低 CSDN 将批量请求误判为异常流量的概率

## 快速开始

项目需要 Python 3.12 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

如果需要 PDF，请在项目目录的 PowerShell 中安装 Chromium。HTML 和 EPUB 可直接使用。

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD ".playwright-browsers"
python -m playwright install chromium
```

运行 `python -m uvicorn app.main:app --reload`，打开 `http://127.0.0.1:8000/` 使用。可访问 `http://127.0.0.1:8000/health` 检查服务状态。

选择「单篇下载」或「专题下载」，粘贴对应地址并选择格式。任务完成后可直接打开本地文件，也可以在「下载记录」里再次打开。专题运行时，返回专题页即可找到当前任务。

专题功能验收期间，每次默认只下载原顺序的前五篇，产物独立保存。需要恢复全量下载时，在启动服务的 PowerShell 窗口设置 `$env:CSDN2LOCAL_TOPIC_ARTICLE_LIMIT = "0"` 后重新启动服务。

程序默认使用 Chrome/157 风格的 User-Agent；如果本机浏览器版本变化或站点仍然拦截，可以在启动前设置 `$env:CSDN2LOCAL_USER_AGENT` 覆盖请求头。

如果专题目录可以读取，但个别文章返回 HTTP 521，可以在结果页点击「打开原文」，用浏览器将能正常查看的文章另存为「网页，仅 HTML」。按地址末尾的文章 ID 命名，例如 `148028338.html`。在「补充浏览器另存的文章」中选择文件后，按原参数重新下载专题。

## 文档

- [项目需求概述](doc/requirements/project-overview.md)
- [项目交接记录](doc/requirements/handoff.md)
- [本地开发说明](doc/development.md)
- [OpenSpec 主规格和归档](openspec/README.md)

## 项目边界

当前版本只处理无需登录即可访问的公开文章，并保存到本地。单篇下载在提交后直接返回结果，专题下载在后台执行。多个独立 URL 的批量导入、正文全文搜索和外部存储上传属于后续迭代。
