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

## 快速开始

项目需要 Python 3.12 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/` 使用，访问 `http://127.0.0.1:8000/health` 检查服务状态。

## 文档

- [项目需求概述](doc/requirements/project-overview.md)
- [项目交接记录](doc/requirements/handoff.md)
- [本地开发说明](doc/development.md)
- [OpenSpec 主规格和归档](openspec/README.md)

## 项目边界

当前版本只处理无需登录即可访问的公开文章，采用同步下载并保存到本地。多个独立 URL 的批量导入、正文全文搜索和外部存储上传属于后续迭代。
