## Why

长文章中的代码块会占用大量页面空间，影响正文阅读和查找。离线 HTML 需要提供代码块折叠能力，同时保持默认展开，确保文章打开后内容完整、PDF 输出不丢失代码。

## What Changes

- 将每个代码块包装为可折叠的 HTML `details` 区域。
- 默认展开代码块，用户可点击标题收起或展开。
- 保留现有暗色背景、等宽字体、空格、换行和边框字符。
- 打印/PDF 时保持代码内容可见，不把折叠状态造成内容丢失。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本变更只增强离线 HTML 的阅读交互，不改变归档内容契约。

## Impact

- 修改 `app/parser.py` 生成的离线 HTML 结构和样式。
- 增加代码块折叠及打印显示的回归测试。
