# csdn2local OpenSpec 需求索引

初始版本包含三项需求。每项在 `changes/` 下有一份完整的提案、规格、设计和任务清单。

## 三项产品需求

| 需求 | 范围 | 规格入口 |
| --- | --- | --- |
| 单个网页下载 | 公开 CSDN 文章的正文提取、带原文地址的离线导出、本地检索和旧归档迁移 | [规格](changes/download-single-page/specs/csdn-single-url-download/spec.md) · [任务](changes/download-single-page/tasks.md) |
| 栏目批量下载 | 按顺序归档 CSDN 专栏或专题，保留专题和逐篇原文地址，支持进度、篇数与格式版本及逐篇补档 | [规格](changes/download-csdn-topic/specs/csdn-topic-download/spec.md) · [任务](changes/download-csdn-topic/tasks.md) |
| 样式优化 | 统一首屏操作、状态反馈、下载记录筛选、键盘操作和窄屏布局 | [规格](changes/streamline-archive-workflows/specs/frontend-experience/spec.md) · [任务](changes/streamline-archive-workflows/tasks.md) |

三个初始需求均保留在 `changes/` 等待用户验收。用户确认上线后统一同步至 `specs/` 并归档。

## 后续迭代规则

1. 每个独立需求创建一份 OpenSpec 变更，先明确需求、设计和任务。
2. 在原变更里记录上线前的缺陷、修复任务和复测结果。
3. 修复相关缺陷并通过测试和验收，交由用户确认已达到可上线状态。
4. 用户确认后，统一同步主规格并归档该需求。

项目文档使用中文维护；代码、接口名称和 OpenSpec 标题可保留英文，以便开源协作和工具校验。
