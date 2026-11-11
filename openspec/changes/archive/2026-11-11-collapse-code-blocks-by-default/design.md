## Context

当前代码块使用 `<details class="code-block" open>`，因此进入文章时全部展开。HTML 原生 details 不需要 JavaScript 即可支持折叠；只需删除 `open` 属性，并在打印样式中显式显示关闭 details 的内容。

## Goals / Non-Goals

**Goals:**

- 网页打开时所有代码块默认收起。
- 用户可逐个点击标题展开或再次收起。
- PDF 和打印输出仍显示完整代码。

**Non-Goals:**

- 不增加全部展开/全部收起按钮。
- 不改变代码文本和代码块样式。

## Decisions

- 生成 `<details class="code-block">`，不设置 `open` 属性。
- 保留现有 `summary` 标题作为唯一交互入口。
- 在 `@media print` 中设置代码块及其 `pre` 为可见，并隐藏 summary 控件，保证打印内容完整。

## Risks / Trade-offs

- **用户第一次查看代码需要点击展开** → 标题栏保持明显的展开指示和“代码块 N”文字。
- **浏览器打印对 details 的默认行为不同** → 使用打印媒体 CSS 显式覆盖关闭状态。

## Migration Plan

无需数据迁移。重新下载文章即可生成默认收起的 HTML；已有 HTML 需要重新生成。
