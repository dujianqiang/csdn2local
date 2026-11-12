## 1. Topic Discovery and Models

- [x] 1.1 Add topic URL validation and ordered article-link extraction with normalized-URL deduplication.
- [x] 1.2 Define topic metadata, ordered article result, failure information, selected output format, and concurrency settings.
- [x] 1.3 Add validation for the single output format (`html`, `epub`, or `pdf`) and positive concurrency values with default `1`.

## 2. Batch Download Orchestration

- [x] 2.1 Implement bounded topic article downloads using the configured concurrency while retaining each article's original index.
- [x] 2.2 Reuse the existing single-article fetching, parsing, resource, and normalized-content pipeline for each topic article.
- [x] 2.3 Continue processing after individual article failures and collect ordered success/failure results for the final navigation.
- [x] 2.4 Add topic staging-directory storage, metadata persistence, and safe commit behavior for a usable partial or complete result.

## 3. Topic Outputs and Navigation

- [x] 3.1 Generate one combined HTML topic document with an ordered navigation and internal article anchors.
- [x] 3.2 Generate one EPUB 3 topic file with ordered chapters, local resources, and `nav.xhtml` navigation.
- [x] 3.3 Generate one PDF topic file from the combined offline document with an ordered visible/clickable contents section.
- [x] 3.4 Ensure failed articles remain represented in ordered metadata/navigation without creating broken links.

## 4. Web Interface

- [x] 4.1 Add shared navigation between the existing single-address page and the new topic-download page.
- [x] 4.2 Add the topic form with topic URL, single-select output format, and editable concurrency defaulting to `1`.
- [x] 4.3 Add topic processing results showing article order, successful outputs, failures, retry information, and local output links.
- [x] 4.4 Preserve existing single-address download, local file list, and search behavior.

## 5. Verification and Documentation

- [x] 5.1 Add topic parser tests for ordered links, duplicate URLs, invalid topics, and access failures.
- [x] 5.2 Add orchestration tests for concurrency configuration, order preservation, and continuation after article failures.
- [x] 5.3 Add HTML, EPUB, and PDF output tests for navigation, local links, article order, and single-format selection.
- [x] 5.4 Add Web tests for page switching, form validation, default concurrency, topic results, and unchanged single download behavior.
- [x] 5.5 Run OpenSpec validation and the full test suite, then update the open-source README and handoff documentation.

## 6. 验收期间的修复与复测

- [x] 6.1 单篇和专题共用文章抓取、正文解析及资源下载方法，复用归档存储方法。
- [x] 6.2 增加回归测试，验证两个入口调用同一方法，专题并行下载不产生独立的单篇归档记录。
- [x] 6.3 处理共享抓取器的 TLS EOF，增加有限重试及失败提示。
- [x] 6.4 验证连接阶段和正文读取阶段的重试、持续断连的提示及证书错误处理。完整自动化测试共 32 项通过。
- [x] 6.5 用用户提供的实际专题链接复测：识别到 30 篇；请求上下文优化后按试下载上限处理前 5 篇，5 篇均成功并生成 HTML。
- [ ] 6.6 完成缺陷修复和复测，由用户验收进度显示、文章顺序、导航和单选导出，并确认达到可上线状态。确认后由用户统一同步主规格和归档。

## 7. 专题进度页面

- [x] 7.1 提交后立即打开任务进度页，记录阶段、处理篇数和耗时。
- [x] 7.2 自动刷新进度，完成后显示输出或失败原因，保留原有重试入口。
- [x] 7.3 验证并行任务及时更新进度、导出仍按原顺序排列、刷新进度页不会重复下载。完整自动化测试共 34 项通过。

## 8. 限量试下载

- [x] 8.1 验收期间默认下载专题的前两篇，进度和结果标注范围，测试产物独立保存。
- [x] 8.2 验证默认限量和设为 `0` 后的全量下载。35 项自动化测试通过。
- [ ] 8.3 上线前解除默认限量，实际复测完整专题后再确认达到可上线状态。
- [x] 8.4 将试下载默认上限调整为 5 篇。原专题实测识别到 30 篇并处理前 5 篇，5 篇均返回 HTTP 521，未生成 HTML。成功导出仍待 6.5 复测。

## 9. 专栏目录提取修复

- [x] 9.1 修复专栏抓取误将侧栏文章加入列表的问题，按「专栏收录文章」确定标题、顺序和试下载范围。
- [x] 9.2 增加含侧栏及缺少目录的回归样例，实测原专栏正确识别到 30 篇并选中目录前两篇。
- [x] 9.3 在单篇与专题共用的抓取器中对 HTTP 521 增加有限重试，验证恢复和持续失败两种情况。
- [x] 9.4 部分成功页提供使用原参数重新下载的入口。

实测两篇正确的文章分别请求时均能返回页面。一次完整试下载保存了第 2 篇并生成 HTML，第 1 篇连续出现 TLS EOF。两篇在同一次任务中均成功仍待复测。自动化测试 39 项通过，OpenSpec 严格校验通过。

## 10. 分批下载与站点防护提示

- [x] 10.1 每批按并行数量处理，批次之间等待 1 秒，并验证最后一批结束后直接导出。
- [x] 10.2 识别站点防护返回的 HTTP 521，提示用户并停止对该页面的自动重试。

41 项自动化测试通过。首次原专题实测识别到 30 篇，按并行数 1 分批处理前 5 篇时均收到 HTTP 521；后续请求上下文优化已完成实际复测并恢复成功导出。

## 11. 用浏览器保存的 HTML 补充文章

- [x] 11.1 接收用户另存的 HTML，核对文章 ID，并复用单篇正文处理流程。
- [x] 11.2 在专题提交和失败结果页提供补充入口，显示失败文章的原文链接。
- [x] 11.3 模拟文章请求被拦截，验证上传文件后按专题原顺序导出。44 项自动化测试通过，OpenSpec 校验通过。真实浏览器另存文件待验收。
- [x] 11.4 模拟文章全部返回 HTTP 521，通过失败结果页逆序提交两份 HTML，打开导出链接并确认正文按专题原顺序排列。45 项自动化测试通过。

## 12. 真实浏览器请求上下文优化

- [x] 12.1 将过期固定 User-Agent 改为可配置的现代 Chrome User-Agent，并为标准 HTTP 请求补充文档导航请求头。
- [x] 12.2 专题文章请求携带专题页面 Referer，增加请求头和上下文传递的回归测试，同时保持单篇入口不伪造 Referer。46 项自动化测试通过。
- [x] 12.3 使用用户提供的 `category_12978516.html` 实际专题复测前五篇：识别 30 篇，前 5 篇全部返回 200，完整生成 `topic.html`。
- [ ] 12.4 更新使用说明和交接记录，保留仍被站点拦截时的浏览器另存 HTML 补救路径；由用户验收后确认是否达到可上线状态。

## 13. 从专题结果页打开文章

- [x] 13.1 将 HTML 专题结果页中已归档的文章标题链接到本地输出的对应正文，保留失败文章的原文入口。
- [x] 13.2 验证结果页链接能访问本地输出并匹配对应正文锚点。已有的 Go 性能优化专题 HTML 中，前五篇标题均匹配本地正文。全套 46 项测试通过。

## 14. 专题下载记录

- [x] 14.1 从已有专题归档读取记录，在专题页按保存时间倒序展示并链接本地输出。
- [x] 14.2 验证旧归档可直接打开、试下载标识、空状态及缺失文件处理。项目中 4 份已有归档的本地链接均可访问，完整测试 47 项通过。
