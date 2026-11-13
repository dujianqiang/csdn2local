## Purpose

栏目批量下载支持从一个公开的 CSDN 专栏或专题地址归档多篇文章，保留原始顺序，并生成带目录的离线文件。下载进度、已保存版本和失败文章的处理结果可在网页查看。

## ADDED Requirements

### Requirement: Download a CSDN topic as an ordered offline publication

系统 SHALL 接受一个公开可访问的 CSDN 专栏或专题地址，识别其中的文章并按原始顺序生成离线内容。系统 SHALL 支持配置下载篇数和并行数量，并允许每次选择一种带目录的输出格式，包括 HTML、EPUB、PDF 和 Markdown。

#### Scenario: Submit a public topic URL

- **WHEN** 用户提交一个公开可访问的 CSDN 专题地址
- **THEN** 系统立即打开该任务的进度页，后台识别专题文章，并按用户选择生成专题输出

#### Scenario: Follow topic download progress

- **WHEN** 专题下载仍在执行
- **THEN** 进度页自动更新当前阶段和耗时，文章列表确定后显示已处理篇数、总篇数和失败篇数

#### Scenario: Show the final result

- **WHEN** 专题任务完成、部分成功或失败
- **THEN** 进度页显示最终结果、可用的输出链接或失败原因，刷新页面可以查看同一个任务

#### Scenario: Preserve the topic article order

- **WHEN** 专题页面包含多篇文章
- **THEN** 系统按照专题页面中的原始顺序处理文章，并在导航和最终输出中保持相同顺序

#### Scenario: Read only the CSDN column article list

- **WHEN** CSDN 专栏页面同时包含专栏目录和侧栏的热门文章、评论链接
- **THEN** 系统仅从「专栏收录文章」提取链接，以该列表的顺序和篇数作为试下载及全量下载的依据

#### Scenario: Configure topic download concurrency

- **WHEN** 用户未修改并行数量或设置一个有效的并行数量
- **THEN** 系统分别使用默认并行数量 1 或用户设置的数量下载文章，同时保持导航和最终输出的专题原始顺序

#### Scenario: Pause between download batches

- **WHEN** 专题需要处理多批文章
- **THEN** 系统按设置的并行数量分批处理，每批全部结束后等待 1 秒再开始下一批

#### Scenario: Reject an invalid concurrency value

- **WHEN** 用户设置的并行数量不是有效的正整数
- **THEN** 系统拒绝该参数并提示用户输入有效的并行数量

#### Scenario: Continue after an individual article failure

- **WHEN** 专题中的某篇文章无法访问、解析或生成
- **THEN** 系统继续处理其余文章，保留成功内容，在对应顺序位置报告失败文章及原因，不让整个专题任务直接失败

#### Scenario: Use HTML saved by the user for an article

- **WHEN** 用户为专题中的文章提供浏览器另存的 HTML
- **THEN** 系统按文章 ID 匹配文件，复用正文和资源处理流程，并把文章合并到专题的原始位置

#### Scenario: Recover from a transient page disconnect

- **WHEN** 专题目录或文章请求出现 TLS EOF、连接重置或正文未完整接收
- **THEN** 系统在递增等待后重新请求，次数耗尽时保留具体失败原因和逐篇恢复入口

#### Scenario: Import saved HTML for one failed article

- **WHEN** 用户在失败行提交与该文章匹配的浏览器另存 HTML
- **THEN** 系统只处理所选文章，并使用已归档的正文重建同一专题产物

#### Scenario: Publish a repaired topic when Windows prevents moving the staging directory

- **WHEN** 重试已生成完整产物，且 Windows 拒绝移动可读取的暂存目录
- **THEN** 系统重试目录替换，必要时使用完整副本发布到原归档路径；发布失败时保护原归档及其备份

#### Scenario: Generate one HTML topic publication

- **WHEN** 用户选择 HTML 作为专题输出格式
- **THEN** 系统生成一个包含专题导航和文章正文的 HTML 文件，导航项可以跳转到对应文章内容地址

#### Scenario: Open an archived article from the topic result page

- **WHEN** 专题结果页或历史详情中有成功归档的文章
- **THEN** 点击成功归档的文章标题打开对应的本地正文。HTML 和 PDF 跳转到专题文件中的文章位置，EPUB 和 Markdown 使用本地阅读视图。失败文章保留失败状态和原文链接

#### Scenario: Open a previously downloaded topic

- **WHEN** 用户进入专题下载页，且本地存在可用的专题归档
- **THEN** 页面按最新匹配版本的保存时间展示专题，同一专题合并为一项，在标题下显示各个匹配版本的格式和篇数范围。点击可进入对应版本的详情、查看逐篇状态并打开本地输出，服务重启后仍可访问

#### Scenario: Set the number of articles to download

- **WHEN** 用户新建或编辑专题任务
- **THEN** 下载篇数可输入非负整数，默认 5，填 0 处理完整专题。提交、修改和重试保留所选值

#### Scenario: Keep exports in different formats

- **WHEN** 用户切换格式重新下载同一专题
- **THEN** 新归档按选中的格式生成，已有其他格式仍在专题下载记录中可见并可打开

#### Scenario: Retry one failed article

- **WHEN** 用户在任务结果或可重建的归档详情中重试一篇失败文章
- **THEN** 系统仅重新处理该文章。成功后按原顺序合并并更新输出，失败时可再次重试且先前可用输出仍可打开

#### Scenario: Show an empty topic history

- **WHEN** 本地没有可用的专题归档
- **THEN** 页面显示暂无专题下载记录，用户可提交新任务

#### Scenario: Generate one e-book topic publication

- **WHEN** 用户选择电子书作为专题输出格式
- **THEN** 系统生成一个电子书文件，电子书目录和正文顺序与专题文章顺序一致，并可从导航进入对应文章

#### Scenario: Generate one PDF e-book topic publication

- **WHEN** 用户选择 PDF 电子书作为专题输出格式
- **THEN** 系统生成一个 PDF 文件，PDF 中包含专题导航或目录，并按专题顺序包含文章内容

#### Scenario: 专题 PDF 首次准备浏览器

- **WHEN** 用户提交专题 PDF 导出或补档，且缺少匹配的 Chromium
- **THEN** 后台任务自动准备浏览器，再生成 PDF。表单和进度页提示首次导出可能需要等待，安装失败时结果页显示原因和补救方式。

#### Scenario: 生成或补齐 Markdown 专题

- **WHEN** 用户选择 Markdown 格式下载专题
- **THEN** 系统生成一个 UTF-8 的 `topic.md`，按专题顺序保留目录、成功文章和失败原因。结果页和历史记录提供包含 `topic.md` 与同级 `assets/` 资源的 ZIP，解压后可离线显示已归档的图片。部分成功时可在历史记录逐篇补齐并下载更新后的 ZIP

#### Scenario: Navigate between topic articles

- **WHEN** 用户打开专题输出中的导航页或导航区域并选择一个文章项
- **THEN** 系统将用户跳转到该文章在专题输出中的本地地址，不要求再次访问 CSDN 原始地址

#### Scenario: Reject an unusable topic

- **WHEN** 专题地址无效、需要登录，或无法识别出任何文章地址
- **THEN** 系统报告明确原因，不生成误导性的成功专题输出

#### Scenario: Request topic articles with navigation context

- **WHEN** 系统从专题目录请求其中的文章
- **THEN** 请求使用可配置的现代浏览器 User-Agent、文档导航请求头，并将专题地址作为同源 Referer；单篇下载没有专题上游地址时不添加伪造 Referer

#### Scenario: Keep a browser-blocked article actionable

- **WHEN** 文章在带导航上下文的请求下仍被 CSDN 安全防护拦截
- **THEN** 系统保留该文章的原始顺序和失败原因，结果页提供打开原文及上传浏览器另存 HTML 的补救入口，不把失败文章误报为成功

### Requirement: 专题归档按篇数和格式存放

系统 SHALL 在 `data/topics/` 下为同一专题复用归档目录，按下载篇数和格式保存各个版本。

#### Scenario: 保存专题版本

- **WHEN** 用户再次成功保存相同篇数及格式的专题
- **THEN** 系统更新对应版本的产物、元数据和资源，保留其他篇数或格式版本

#### Scenario: 专题标题发生变化

- **WHEN** 同一专题以新标题重新下载
- **THEN** 继续使用原专题目录，网页展示最新保存的标题

#### Scenario: 迁移同一规格的多份旧归档

- **WHEN** 迁移发现同一专题、同一篇数、同一格式的多个旧目录
- **THEN** 系统保留每一份。有新布局版本时保留当前版本，否则最近保存的旧归档成为当前版本，其余在详情中可打开

### Requirement: 专题下载文件标注原始 URL

系统 SHALL 在新生成的专题 HTML、PDF、EPUB 和 Markdown 正文中显示可点击的专题和文章来源地址。

#### Scenario: 查看专题文件的来源

- **WHEN** 用户打开新生成的专题文件
- **THEN** 专题标题下显示专题或栏目 URL，下载成功的各篇文章标题下显示对应文章的 URL，失败条目显示对应文章的 URL 和失败原因

#### Scenario: 补档后查看文章来源

- **WHEN** 用户成功重试或从浏览器另存的 HTML 补齐一篇失败文章
- **THEN** 更新后的专题仍显示专题 URL 和对应的逐篇 URL，每篇文章的标注显示一次
