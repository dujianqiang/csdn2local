## Why

文章索引可能包含本地归档路径和测试记录。现有的 `data/` 忽略规则覆盖默认数据库位置，数据库副本放到仓库其他目录时需要同样的保护。

## What Changes

- 按文件名忽略文章索引数据库及其 SQLite 辅助文件。
- 沿用应用现有的建库逻辑，保留本地数据库。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。

## Impact

影响 Git 的忽略规则。应用继续使用现有的索引初始化和存储逻辑。
