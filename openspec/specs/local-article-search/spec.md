# local-article-search Specification

## Purpose

为已保存的本地文章提供一个简单、可检索的入口，帮助用户通过少量元数据快速定位并打开可用的离线文章文件。

## Requirements

### Requirement: Provide a single metadata search entry

The system SHALL provide one keyword search input alongside a list of downloaded articles. The search SHALL perform fuzzy matching against article title, source domain, original URL, author, and tags. When the keyword is empty, the page SHALL show all downloaded articles; when a keyword is provided, it SHALL show only matching articles. The search SHALL NOT require full-text indexing of article bodies in the first phase.

#### Scenario: Search by metadata keyword

- **WHEN** the user submits a keyword matching any supported metadata field
- **THEN** the system returns matching archived articles in the downloaded-file list

#### Scenario: Search with no match

- **WHEN** the submitted keyword matches no supported metadata field
- **THEN** the system reports that no archived article was found

#### Scenario: Open the page without a keyword

- **WHEN** the user opens the home page without entering a keyword
- **THEN** the system displays all downloaded articles in the list

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

### Requirement: Browse downloaded archive files

The system SHALL display each indexed downloaded article with only its title and a local file address. The list SHALL be ordered by save time from newest to oldest. When an HTML file exists, the address MUST open the local HTML file; when HTML is absent but PDF exists, the address MUST open the local PDF file.

#### Scenario: List downloaded articles by latest save time

- **WHEN** multiple downloaded articles exist
- **THEN** the list displays them in descending order of their save time

#### Scenario: Open a downloaded HTML article

- **WHEN** a listed archive contains an HTML file
- **THEN** the article address opens the local HTML file

#### Scenario: Fall back to a downloaded PDF

- **WHEN** a listed archive contains no HTML file but contains a PDF file
- **THEN** the article address opens the local PDF file

#### Scenario: Show an empty downloaded-file list

- **WHEN** no downloaded article exists
- **THEN** the page displays an explicit empty-state message instead of an empty list
