## Purpose

为已保存的本地文章提供一个简单、可检索的入口，帮助用户通过少量元数据快速定位并打开可用的离线文章文件。

## ADDED Requirements

### Requirement: Provide a single metadata search entry

The system SHALL provide one keyword search input rather than an article-list homepage. The search SHALL perform fuzzy matching against article title, source domain, original URL, author, and tags, and SHALL NOT require full-text indexing of article bodies in the first phase.

#### Scenario: Search by metadata keyword

- **WHEN** the user submits a keyword matching any supported metadata field
- **THEN** the system returns matching archived articles

#### Scenario: Search with no match

- **WHEN** the submitted keyword matches no supported metadata field
- **THEN** the system reports that no archived article was found

#### Scenario: Search does not inspect body text

- **WHEN** a keyword appears only in the article body and not in supported metadata
- **THEN** the system does not require the article to match in the first phase

### Requirement: Link search results to the best available local file

The system SHALL display only the article title and a local address for each search result. When an HTML file exists, the address MUST open the local HTML file; when HTML is absent but PDF exists, the address MUST open the local PDF file.

#### Scenario: HTML is available

- **WHEN** a matching archive contains an HTML file
- **THEN** the result displays the article title and a link to the local HTML file

#### Scenario: Only PDF is available

- **WHEN** a matching archive contains no HTML file but contains a PDF file
- **THEN** the result displays the article title and a link to the local PDF file
