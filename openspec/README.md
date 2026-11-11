# csdn 单个连接下载 OpenSpec 文档

本目录维护项目唯一的首期产品需求及后续迭代记录。

## 当前结构

- `specs/csdn-single-url-download/spec.md`：项目唯一主规格，描述首期完整需求。
- `changes/archive/2026-11-11-csdn-single-url-download/`：符合 OpenSpec 框架格式的首期实现历史归档目录，包含 `.openspec.yaml`、proposal、specs、design 和 tasks。
- `config.yaml`：OpenSpec 工作流和项目上下文配置。

首期开发过程中曾按问题和实现细节产生多个临时变更目录。它们已经合并为一个项目需求和一个符合 OpenSpec 规范的历史归档变更目录，后续不要为同一首期需求重复创建独立变更。

## 后续迭代规则

后续新增功能、问题修复或结构调整统一遵循 OpenSpec：

1. 基于唯一主规格创建一个新的变更。
2. 完成 proposal、specs、design 和 tasks 后再实现。
3. 实现后运行测试和 OpenSpec 校验。
4. 完成变更后归档，并保持主规格与代码一致。

项目文档使用中文维护；代码、接口名称和 OpenSpec 标题可保留英文，以便开源协作和工具校验。
