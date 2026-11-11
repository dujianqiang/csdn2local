# csdn 单个连接下载 OpenSpec 文档

本目录维护项目唯一的首期产品需求及后续迭代记录。

## 当前结构

- `specs/csdn-single-url-download/spec.md`：单篇文章下载主规格。
- `specs/csdn-topic-download/spec.md`：CSDN 专题下载主规格。
- `changes/archive/2026-11-11-csdn-single-url-download/`：单篇下载实现历史归档目录。
- `changes/archive/2026-11-11-download-csdn-topic/`：专题下载实现历史归档目录。
- `config.yaml`：OpenSpec 工作流和项目上下文配置。

首期单篇下载和后续专题下载都保留为完整的 OpenSpec 变更归档目录，后续新增功能应基于对应主规格创建新的变更。

## 后续迭代规则

后续新增功能、问题修复或结构调整统一遵循 OpenSpec：

1. 基于唯一主规格创建一个新的变更。
2. 完成 proposal、specs、design 和 tasks 后再实现。
3. 实现后运行测试和 OpenSpec 校验。
4. 完成变更后归档，并保持主规格与代码一致。

项目文档使用中文维护；代码、接口名称和 OpenSpec 标题可保留英文，以便开源协作和工具校验。
