## Why

公开 CSDN 文章可能下线。用户需要通过一个链接保存可以离线阅读、打印或编辑的本地副本。

## What Changes

- 接收单个公开文章链接，提取正文和必要资源，每次在网页选择 HTML、PDF 或 Markdown 中的一种。
- 在各格式的文章标题下显示可点击的原始地址。
- 重新下载时保留其他格式及其离线资源，下载记录支持关键词搜索和[按格式筛选](../streamline-archive-workflows/proposal.md)。
- 迁移旧版单篇和栏目归档，保留历史文件和旧链接。
- 由应用初始化本地索引，并在 Git 中忽略索引数据库及其辅助文件。

## Capabilities

### New Capabilities

- `csdn-single-url-download`（单个网页下载）：公开文章下载、导出、本地检索和共用的旧归档迁移。

## Impact

涉及单篇下载入口、正文与资源处理、格式导出、归档存储、文件访问、SQLite 索引和 Git 忽略规则。
