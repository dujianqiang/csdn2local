## Why

代码块较多的文章打开后会占据很长页面，影响正文浏览和搜索。现有折叠功能默认展开，用户希望文章打开时代码块默认收起，需要时再点击展开。

## What Changes

- 移除代码块 `details` 的默认展开状态。
- 保留代码块标题栏和点击展开/收起能力。
- 打印和 PDF 输出时强制显示代码内容，不受网页折叠状态影响。
- 更新回归测试和用户文章 HTML。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本变更只调整已有折叠交互的默认状态。

## Impact

- 修改 `app/parser.py` 生成的代码块 HTML 和打印 CSS。
- 更新代码块输出测试。
