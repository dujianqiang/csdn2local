## Context

正文清理在 `app/parser.py` 中通过 CSS 选择器移除网页非正文节点。CSDN 代码高亮使用 Prism 风格的 `span.token.comment` 表示源代码注释；该节点与网页评论区共享 `comment` class 片段，但语义完全不同。

## Goals / Non-Goals

**Goals:**

- 只移除明确的评论容器，不删除代码块中的注释 token。
- 保持现有正文提取、资源下载和输出流程不变。

**Non-Goals:**

- 不重新设计正文识别算法。
- 不恢复已经从旧归档中删除的内容；修复后重新下载即可生成完整版本。

## Decisions

- 删除 `[class*='comment']` 和过宽的 `.comment` 清理规则。
- 使用带容器语义的精确选择器，例如 `div.comment-box`、`div.comment-list`、`section.comment` 及明确的 comment id，避免匹配 `span.token.comment`。
- 在 HTML fixture 中同时放入真正的评论容器和代码注释 token，断言前者被删除、后者保留。

## Risks / Trade-offs

- **不同 CSDN 模板的评论容器命名不同** → 保留多个明确容器选择器，并让正文 fixture 测试覆盖已知结构。
- **旧归档不会自动补全** → 修复后由用户重新下载同一 URL，按既有覆盖规则生成最新归档。

## Migration Plan

无需数据迁移。更新服务并重新下载文章即可覆盖旧归档；SQLite 索引结构不变。
