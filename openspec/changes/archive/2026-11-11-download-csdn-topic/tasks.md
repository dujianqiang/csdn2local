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
