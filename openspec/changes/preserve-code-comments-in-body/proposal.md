## Why

正文清理规则把所有带有 `comment` class 的节点当作网页评论区删除，但代码高亮也使用 `token comment` 表示源代码注释。结果是文章中的代码注释被错误删除，导致归档资料不完整。

## What Changes

- 将评论区清理规则从宽泛的 class 匹配改为明确的评论容器匹配。
- 保留代码块中的语法高亮注释节点。
- 增加包含 `token comment` 的正文回归测试，并重新验证用户提供的文章。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。现有归档规格已经要求保留正文和代码内容；本变更只修复实现与既有要求不一致的问题。

## Impact

- 修改 `app/parser.py` 的正文清理选择器。
- 增加正文提取回归测试。
- 不改变 Web API、归档目录结构、文件格式或搜索行为。
