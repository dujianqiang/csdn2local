# 本地开发

项目需要 Python 3.12 或更高版本。在项目目录运行当前系统对应的命令。安装开发依赖后，先按 [README 的 PDF 安装步骤](../README.md#启用-pdf) 安装 Chromium，再运行完整测试。

## Windows（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Linux 和 macOS（终端）

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
```

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m uvicorn app.main:app --reload
```

## 验证

启动后访问 `http://127.0.0.1:8000/health` 检查服务状态。

修改规格或变更工件后，在仓库根目录使用 OpenSpec CLI 校验。

```text
openspec validate --all --strict --no-interactive
```

产品需求、当前变更和验收流程见 [OpenSpec 需求索引](../openspec/README.md)。
