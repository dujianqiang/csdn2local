# csdn 单个连接下载 OpenSpec 文档

本目录维护已验收的产品规格和正在推进的需求。

## 当前结构

- [单篇文章下载主规格](specs/csdn-single-url-download/spec.md)
- [CSDN 专题下载变更与验收清单](changes/download-csdn-topic/tasks.md)
- `changes/archive/2026-11-11-csdn-single-url-download/`：单篇下载实现历史归档目录。
- `config.yaml`：OpenSpec 工作流和项目上下文配置。

## 后续迭代规则

1. 每个独立需求创建一份 OpenSpec 变更，先明确需求、设计和任务。
2. 在原变更里记录上线前的缺陷、修复任务和复测结果。
3. 修复相关缺陷并通过测试和验收，交由用户确认已达到可上线状态。
4. 用户确认后，统一同步主规格并归档该需求。

项目文档使用中文维护；代码、接口名称和 OpenSpec 标题可保留英文，以便开源协作和工具校验。
