# csdn-topic-download Specification

## Purpose
为 CSDN 专题提供一次提交、批量归档和统一阅读的能力，保留专题文章原始顺序，并生成带导航的单一离线输出文件。

## Requirements

### Requirement: Download a CSDN topic as an ordered offline publication

系统 SHALL 接受一个公开可访问的 CSDN 专题地址，识别其中的文章地址并按照专题页面提供的顺序批量下载。系统 SHALL 允许用户配置专题文章下载的并行数量，默认值为 1；无论并行数量如何设置，导航和最终输出都必须保持专题原始顺序。系统 SHALL 允许用户选择一种专题输出：单一 HTML、单一电子书或单一 PDF 电子书；每种输出都必须包含可跳转到专题文章的导航。

#### Scenario: Submit a public topic URL

- **WHEN** 用户提交一个公开可访问的 CSDN 专题地址
- **THEN** 系统识别专题文章、展示或开始处理文章顺序，并按用户选择生成专题输出

#### Scenario: Preserve the topic article order

- **WHEN** 专题页面包含多篇文章
- **THEN** 系统按照专题页面中的原始顺序处理文章，并在导航和最终输出中保持相同顺序

#### Scenario: Configure topic download concurrency

- **WHEN** 用户未修改并行数量或设置一个有效的并行数量
- **THEN** 系统分别使用默认并行数量 1 或用户设置的数量下载文章，同时保持导航和最终输出的专题原始顺序

#### Scenario: Reject an invalid concurrency value

- **WHEN** 用户设置的并行数量不是有效的正整数
- **THEN** 系统拒绝该参数并提示用户输入有效的并行数量

#### Scenario: Continue after an individual article failure

- **WHEN** 专题中的某篇文章无法访问、解析或生成
- **THEN** 系统继续处理其余文章，保留成功内容，在对应顺序位置报告失败文章及原因，不让整个专题任务直接失败

#### Scenario: Generate one HTML topic publication

- **WHEN** 用户选择 HTML 作为专题输出格式
- **THEN** 系统生成一个包含专题导航和文章正文的 HTML 文件，导航项可以跳转到对应文章内容地址

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
