## Context

`ArticleIndex` 会创建数据库文件和表。当前默认路径是 `data/.internal/index.sqlite3`，旧版使用 `data/index.sqlite3`。本地和远程分支的可达提交中均未发现索引数据库，当前 Git 索引也未跟踪该文件。

## Decisions

- 保留 `data/` 忽略规则，增加不含目录分隔符的规则，以覆盖仓库各层级的 `index.sqlite3`、`index.sqlite`、`index.sqllite` 及其 WAL、SHM 和回滚日志。
- 新环境由应用初始化数据库。现有数据库原地保留，沿用应用的旧库兼容逻辑。

## Risks / Trade-offs

- `.gitignore` 作用于未跟踪文件。通过 Git 索引和可达历史核对本次涉及的文件，普通暂存行为在隔离仓库中验证。
