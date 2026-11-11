# csdn 单个连接下载：初始版本归档

## 归档说明

- 项目名称：`csdn 单个连接下载`
- 归档日期：2026-11-11
- 归档类型：首期需求及其实现历史的合并归档
- 当前主规格：`openspec/specs/csdn-single-url-download/spec.md`

本文件合并首期开发过程中产生的所有 OpenSpec 变更记录。它们原本被拆成多个目录，但都属于同一个首期需求，不代表多个独立产品需求。

## 项目目标

将一个公开 CSDN 文章 URL 保存为本地 HTML、PDF 或两者，保留正文和必要资源，避免网站停止运营、服务调整或文章下线后无法继续访问，并为后续上传到其他平台提供可迁移的本地归档。

## 最终实现范围

- 提供本地 FastAPI Web 服务。
- 每次支持一个公开 CSDN 文章 URL，同步完成下载和生成。
- 默认生成 HTML，可选 PDF，或同时生成 HTML 和 PDF。
- 只提取正文，不下载评论、广告、推荐、侧边栏等非正文内容。
- 正文图片等资源保存到文章目录的 `assets/`，HTML 使用相对路径。
- 代码注释、换行、缩进、空白及 ASCII/Unicode 边框字符保持不丢失。
- HTML 代码块使用深色样式，默认折叠，可点击展开；打印和 PDF 中代码保持可见。
- 公开页面使用兼容性更好的 HTTPS 抓取方式，并准确识别登录限制。
- 文件保存到 `data/<domain>/<article-key>/`，重复 URL 覆盖旧归档。
- 资源或单一输出格式失败时保留其他可用产物并返回部分成功信息。
- 首页展示已下载文件列表，按保存时间倒序；支持基于标题、域名、URL、作者和标签的元数据搜索。
- 搜索和列表只展示标题及受控的本地 HTML/PDF 地址。

## 文件布局

```text
data/
└── <domain>/
    └── <article-id>_<sanitized-title>/
        ├── article.html
        ├── article.pdf
        ├── metadata.json
        └── assets/
```

## 初始版本开发历史

| 阶段 | 原变更目录 | 最终纳入内容 |
| --- | --- | --- |
| 1 | `save-csdn-articles-locally` | 单 URL 归档、正文提取、HTML/PDF、本地存储、索引和搜索基础 |
| 2 | `fix-public-csdn-access-detection` | 准确区分公开页面与明确登录限制 |
| 3 | `preserve-code-comments-in-body` | 保留代码中的语法高亮注释节点 |
| 4 | `preserve-code-block-visual-style` | 保留深色代码块、空白、换行和边框字符 |
| 5 | `use-compatible-csdn-page-fetch` | 使用兼容性更好的标准库 HTTPS 页面抓取 |
| 6 | `collapsible-code-blocks` | 增加代码块展开/折叠交互 |
| 7 | `collapse-code-blocks-by-default` | 代码块默认折叠，打印/PDF 强制可见 |
| 8 | `add-downloaded-file-list` | 首页已下载文件列表、排序和空状态 |

## 技术设计摘要

- Python 3.12、FastAPI、服务端模板和 SQLite 组成单体本地服务。
- BeautifulSoup/lxml 负责正文解析，Playwright 负责 PDF 生成。
- 文件系统是内容事实来源，SQLite 只保存搜索所需的文章元数据。
- 页面和资源下载采用逐项容错策略；至少一个选择的输出可用时提交归档。
- 所有本地文件访问都经过受控路由，不接受任意文件系统路径。

## 验证结果

- 自动化测试：20 个测试通过。
- OpenSpec 主规格校验：通过。
- 首期主规格已合并为单一文件，历史变更已合并为本归档文件。

## 后续迭代边界

批量导入、正文全文搜索、外部存储上传、版权提示增强和更多页面结构适配属于后续迭代；开始实现前应继续遵循 OpenSpec 流程，并在本项目主规格基础上创建新的变更记录。
