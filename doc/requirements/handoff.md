# csdn2local 1.0 交接

更新于 2026-11-13。

## 当前状态

csdn2local 是本地运行的 FastAPI Web 工具，将公开 CSDN 文章和专题保存为离线文件。1.0 的安装、启动、PDF 配置和操作步骤见 [项目 README](../../README.md)。

- **单篇下载**支持 HTML、PDF、Markdown，每次保存一种格式。归档位于 `data/articles/`，下载记录可按关键词和格式筛选。
- **专题下载**支持 HTML、EPUB、PDF、Markdown。默认处理前 5 篇，填 `0` 处理全部已识别文章。任务在后台执行，按原目录顺序导出，可逐篇重试或导入浏览器另存的 HTML。归档位于 `data/topics/`，按篇数和格式保留不同版本。
- 工作区位于 `dev`，基线提交为 `59e48e4`，另有已修改、已删除和未跟踪文件。相对本地记录的 `origin/dev`，`dev` 领先 11 个提交、落后 1 个提交。接手时以当前工作区和 `git status --short --branch` 为准。
- README 使用产品版本 1.0，`pyproject.toml` 的 Python 包版本目前为 `0.1.0`。如需发布 Python 包，先确认版本号。

## 开发入口

- [app/main.py](../../app/main.py) 提供单篇、专题、进度和文件访问路由。
- [app/archive.py](../../app/archive.py) 负责单篇下载，[app/topic.py](../../app/topic.py) 和 [app/topic_jobs.py](../../app/topic_jobs.py) 负责专题下载和任务状态。
- [app/storage.py](../../app/storage.py) 管理归档目录，[app/index.py](../../app/index.py) 管理单篇归档的 SQLite 搜索索引。
- 安装开发依赖、运行测试和校验规格见 [本地开发说明](../development.md)。

## 验证结果

| 环境 | 结果 |
| --- | --- |
| Windows | `python -m pytest -q` 全部 73 项通过。 |
| Ubuntu 24.04（WSL） | 隔离目录中安装并启动成功，健康检查正常，首页和专题页返回 HTTP 200。装入 Playwright 对应的 Chromium Headless Shell 后，72 项测试通过，1 项 Windows 专属测试跳过。Linux 系统依赖的一键安装命令仍待在干净环境复测。 |
| macOS | 已记录安装、启动和 PDF 配置步骤，待实机验证。 |
| OpenSpec | `openspec validate --all --strict --no-interactive` 校验通过，共 3 项变更。 |

## 接手后的验收

1. **单篇下载**。用真实公开文章 `148010754` 复测在线抓取、PDF 和归档内的原文链接。上次实测返回 HTTP 521。完整验收项见 [单篇下载任务](../../openspec/changes/download-single-page/tasks.md)。
2. **专题下载**。用真实栏目 `12978516` 复测试下载、全量下载、目录与文章顺序、原文链接、Markdown 和逐篇补档。上次识别到 30 篇，首篇 `148028338` 的 HTTPS 连接提前断开。完整验收项见 [专题下载任务](../../openspec/changes/download-csdn-topic/tasks.md)。
3. **界面**。复测窄屏布局、进度反馈，以及用实际归档按文件类型筛选。完整验收项见 [界面优化任务](../../openspec/changes/streamline-archive-workflows/tasks.md)。
4. **跨平台**。在 macOS 实机验证启动和 PDF 导出，在干净的 Linux 环境复测 README 中的 Chromium 系统依赖安装命令。

验收中发现的问题先更新对应的 OpenSpec 变更，再实现、测试并记录结果。三项变更留在 `openspec/changes/`，由用户在验收通过后确认上线，再统一同步主规格并归档。参见 [项目协作规范](../../AGENTS.md) 和 [OpenSpec 需求索引](../../openspec/README.md)。
