# csdn2local 1.0

csdn2local 是一个在本机运行的 CSDN 下载工具。粘贴公开文章或专题的链接，即可将正文、图片和代码保存为离线文件。专题按原目录顺序合并，并生成目录。

| 下载方式 | 支持的链接 | 保存格式 |
| --- | --- | --- |
| 单篇下载 | CSDN 文章页 | HTML、PDF、Markdown |
| 专题下载 | CSDN 专栏或专题目录页 | HTML、EPUB、PDF、Markdown |

每次选择一种格式，默认保存为 HTML。

## 快速开始

需要 Git 和 Python 3.12 或更高版本。先获取项目，再按系统选择启动命令。

```text
git clone https://github.com/dujianqiang/csdn2local.git
cd csdn2local
```

### Windows（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Linux 和 macOS（终端）

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果 Debian 或 Ubuntu 提示缺少 `venv` 或 `ensurepip`，先安装与当前 Python 版本对应的 `venv` 软件包。使用系统自带的 Python 时，软件包名为 `python3-venv`。

启动后，在浏览器访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。在启动服务的终端按 `Ctrl+C` 停止服务。

### 启用 PDF

首次保存 PDF 前，在项目目录安装 Chromium。HTML、EPUB 和 Markdown 可直接使用。

**Windows（PowerShell）**

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD ".playwright-browsers"
.\.venv\Scripts\python.exe -m playwright install chromium
```

**Linux**

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright-browsers" ./.venv/bin/python -m playwright install --with-deps chromium
```

`--with-deps` 会一并安装 Chromium 需要的系统依赖，可能要求管理员权限。

**macOS**

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright-browsers" ./.venv/bin/python -m playwright install chromium
```

PDF 导出支持的系统版本和 Linux 发行版见 [Playwright 系统要求](https://playwright.dev/python/docs/intro#system-requirements)。

## 使用说明

### 单篇下载

1. 打开「单篇下载」，粘贴 CSDN 文章页的链接，例如 `https://blog.csdn.net/<作者>/article/details/<文章ID>`。
2. 选择保存格式，点击「开始保存」，在结果页打开或下载文件。
3. 在「单篇下载记录」中按标题、域名、作者或标签搜索，也可以按文件类型筛选。

### 专题下载

1. 打开「专题下载」，粘贴专栏或专题目录链接。CSDN 专栏链接通常以 `category_<专栏ID>.html` 结尾。
2. 填写下载篇数并选择输出格式。默认下载前 5 篇，填 `0` 下载全部已识别文章。可在「高级设置」中调整并行数量，默认同时下载 1 篇。
3. 点击「开始下载专题」，在进度页查看处理情况。离开后可从专题页返回正在运行的任务。
4. 在结果页打开或下载文件。也可在「专题下载记录」中按文件类型筛选，查看对应篇数和格式的归档。

## 本地归档

- 单篇文章保存在 `data/articles/<文章目录>/`。重新下载会更新选定格式，其他格式继续保留。
- 专题保存在 `data/topics/<专题目录>/<前N篇或全部>/<格式>/`。同一专题的不同篇数和格式分别保存。

归档文件包含 CSDN 原文链接，专题归档也保留各篇文章的原文链接。

从网页下载 Markdown 时会获得 ZIP。解压后打开 `article.md` 或 `topic.md`。移动 HTML 或 Markdown 文件时，将同级的 `assets/` 一起移动，以保留本地图片引用。

## 下载失败时

- 单篇下载失败时，可在结果页查看原因、修改设置或重试。
- 专题中有文章下载失败时，在该文章旁点击「重试这篇」。如果浏览器能打开原文，也可以将原文另存为「网页，仅 HTML」，以文章 ID 命名，例如 `148028338.html`，再通过「导入这篇的 HTML」上传。

## 启动配置

修改下列环境变量后，在同一终端重新启动服务。

| 环境变量 | 用途 |
| --- | --- |
| `CSDN2LOCAL_TOPIC_ARTICLE_LIMIT` | 设置专题表单的默认下载篇数，接受非负整数，默认为 `5` |
| `CSDN2LOCAL_USER_AGENT` | 自定义工具访问 CSDN 网页时发送的浏览器标识（User-Agent）。三个系统都默认发送同一段 Windows 版 Chrome 标识，通常无需设置。 |

## 开发

- 安装开发依赖、运行测试和校验规格，见[本地开发说明](doc/development.md)。
- 项目需求和变更流程见 [OpenSpec 需求索引](openspec/README.md)。

## 项目边界

项目面向无需登录即可访问的公开 CSDN 内容，归档保存在本地。请按原作者的授权范围使用下载内容。
