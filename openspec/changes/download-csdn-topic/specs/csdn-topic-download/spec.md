## Purpose

为 CSDN 专题提供一次提交、批量归档和统一阅读的能力，保留专题文章原始顺序，并生成带导航的单一离线输出文件。

## ADDED Requirements

### Requirement: Download a CSDN topic as an ordered offline publication

系统 SHALL 接受一个公开可访问的 CSDN 专题地址，识别其中的文章地址并按照专题页面提供的顺序批量下载。系统 SHALL 允许用户配置专题文章下载的并行数量，默认值为 1；无论并行数量如何设置，导航和最终输出都必须保持专题原始顺序。系统 SHALL 允许用户选择一种专题输出：单一 HTML、单一电子书或单一 PDF 电子书；每种输出都必须包含可跳转到专题文章的导航。

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

#### Scenario: Generate one HTML topic publication

- **WHEN** 用户选择 HTML 作为专题输出格式
- **THEN** 系统生成一个包含专题导航和文章正文的 HTML 文件，导航项可以跳转到对应文章内容地址

#### Scenario: Open an archived article from the topic result page

- **WHEN** HTML 专题结果页中有成功归档的文章
- **THEN** 点击文章标题直接打开专题 HTML 并跳转到对应正文。失败文章保留失败状态和原文链接

#### Scenario: Open a previously downloaded topic

- **WHEN** 用户进入专题下载页，且本地存在可用的专题归档
- **THEN** 页面按保存时间从新到旧展示归档标题、格式和时间，并标明试下载产物。点击记录直接打开本地输出，服务重启后仍可访问

#### Scenario: Show an empty topic history

- **WHEN** 本地没有可用的专题归档
- **THEN** 页面显示暂无专题下载记录，用户可提交新任务

#### Scenario: Generate one e-book topic publication

- **WHEN** 用户选择电子书作为专题输出格式
- **THEN** 系统生成一个电子书文件，电子书目录和正文顺序与专题文章顺序一致，并可从导航进入对应文章

#### Scenario: Generate one PDF e-book topic publication

- **WHEN** 用户选择 PDF 电子书作为专题输出格式
- **THEN** 系统生成一个 PDF 文件，PDF 中包含专题导航或目录，并按专题顺序包含文章内容

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
