# 本地开发

项目需要 Python 3.12 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m uvicorn app.main:app --reload
```

启动后访问 `http://127.0.0.1:8000/health` 检查服务状态。

PDF 输出依赖 Playwright Chromium。只保存 HTML 时可以不使用 PDF 输出，但安装浏览器后才能启用完整功能。
