## Why

当前离线 HTML 虽然保留了代码块内容，但默认样式较浅，无法体现 CSDN 原页面的深色代码展示效果。用户希望保留截图中的黑色背景、等宽代码排版和 ASCII 边框字符，提升离线阅读的一致性。

## What Changes

- 为离线 HTML 的 `pre`/`code` 增加暗色代码块样式。
- 保留代码块中的换行、缩进、空格和 ASCII/Unicode 边框字符。
- 保持代码块横向滚动，避免长行破坏页面布局。
- 不保存 CSDN 的 VIP、复制按钮和其他页面交互外壳。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本变更只调整已归档 HTML 的展示样式，不改变归档行为契约。

## Impact

- 修改 `app/parser.py` 生成的离线 HTML 样式。
- 增加代码块样式和特殊字符保留的回归测试。
