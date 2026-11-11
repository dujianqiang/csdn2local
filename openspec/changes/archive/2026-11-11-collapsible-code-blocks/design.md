## Context

当前离线 HTML 已有统一代码块样式，但所有代码块始终展开。生成逻辑集中在 `render_article_document`，无需引入 JavaScript 或前端依赖即可使用 HTML 原生 `details/summary` 控件。

## Goals / Non-Goals

**Goals:**

- 让用户可以逐个代码块折叠和展开。
- 默认展开，保证普通阅读、离线打开和 PDF 渲染都能看到代码。
- 让折叠标题与现有暗色代码卡片样式协调。

**Non-Goals:**

- 不增加“一键全部折叠/展开”脚本。
- 不改变代码文本、语法高亮 class 或归档文件结构。

## Decisions

- 在生成 HTML 时解析正文片段，把每个 `pre` 放入 `<details class="code-block" open>`，并生成 `summary` 标题。
- 使用 CSS 设置 summary 的深色标题栏、点击手势和展开后的边框连接；不依赖 JavaScript。
- 在打印媒体样式中隐藏折叠标题但保持 details 内容显示，避免 PDF 出现交互控件或隐藏代码。
- 代码块标题使用“代码块 N”，避免从代码内容猜测标题并保持稳定。

## Risks / Trade-offs

- **部分浏览器对 details 打印行为不同** → 保留 `open` 属性并添加 `@media print` 样式，确保内容默认可见。
- **正文中存在非代码用途的 pre** → 统一视为可折叠的预格式化块，仍保留原始文本和格式。

## Migration Plan

无需数据迁移。重新下载文章即可生成带折叠能力的 HTML；已有 HTML 需要重新生成才能获得新交互。
