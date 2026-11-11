## Purpose

为本地 Web 工具提供可靠的 CSDN 公开文章归档能力，使正文和必要资源能够离线保存，并支持后续迁移到其他存储或平台。

## ADDED Requirements

### Requirement: Accept a public article URL and format selection

The system SHALL accept one publicly accessible CSDN article URL per download request and SHALL allow the user to select HTML, PDF, or both formats. When no format is selected explicitly, the system MUST use HTML.

#### Scenario: Submit a URL with the default format

- **WHEN** the user submits one publicly accessible CSDN article URL without an explicit format
- **THEN** the system synchronously processes the request and attempts to produce an HTML file

#### Scenario: Submit a URL with selected formats

- **WHEN** the user submits one publicly accessible CSDN article URL and selects one or both supported formats
- **THEN** the system synchronously processes the request and attempts to produce exactly the selected formats

#### Scenario: Reject unsupported access scope

- **WHEN** the submitted article requires login or paid access
- **THEN** the system reports that the article is outside the first-phase supported scope and does not treat it as a successful archive

### Requirement: Preserve the article body and relevant resources

The system SHALL archive the article title and正文内容, including正文中的 images, code, and necessary formatting. The system MUST exclude comments, advertisements, recommendations, sidebars, and other non-body page content, and SHALL save body-referenced resources locally for offline use.

#### Scenario: Extract an article page

- **WHEN** a public CSDN article page contains body content and page-level non-body content
- **THEN** the generated archive contains the article body and excludes the non-body content

#### Scenario: Save referenced resources locally

- **WHEN** the article body references images or other required resources
- **THEN** the system saves those resources under the article's local `assets/` directory and generated HTML references them with local relative paths

### Requirement: Store an archive in the defined local layout

The system SHALL store all article files below the project `data/` directory, using the source URL domain as the first-level directory and an article ID plus sanitized title as the article directory name. The system SHALL save searchable metadata including title, author, publication time, tags, original URL, and save time.

#### Scenario: Save a new article

- **WHEN** an article is archived successfully or partially successfully
- **THEN** its generated files, `metadata.json`, and downloaded body resources are stored under `data/<domain>/<article-key>/`

#### Scenario: Article ID is unavailable

- **WHEN** the source page does not expose a usable article ID
- **THEN** the system uses a stable fallback article directory name and records the original URL in metadata

#### Scenario: Archive an existing URL again

- **WHEN** the user archives a URL that already has a local archive
- **THEN** the system replaces the existing archive with the latest result and does not retain an older version as the active archive

### Requirement: Report complete, partial, and failed outcomes

The system SHALL report a specific failure reason and provide a retry action when the archive cannot be completed. Failure to download an individual body resource or generate one selected format MUST NOT discard other successful outputs.

#### Scenario: One resource fails

- **WHEN** an image or other body resource cannot be downloaded
- **THEN** the system keeps the article files that were generated, identifies the missing resource, and reports a partial result

#### Scenario: One selected format fails

- **WHEN** both HTML and PDF are selected and only one format fails to generate
- **THEN** the system preserves the successful format, reports the failed format and reason, and allows the user to retry

#### Scenario: Download fails before an archive is usable

- **WHEN** the system cannot obtain or parse enough content to create a usable selected output
- **THEN** the system reports the concrete failure reason and provides a retry action
