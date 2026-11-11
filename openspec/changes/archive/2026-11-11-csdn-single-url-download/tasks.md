## 1. Project Setup

- [x] 1.1 Initialize the Python Web service and dependency configuration.
- [x] 1.2 Create application modules, configuration, data directory handling, and local entrypoint.
- [x] 1.3 Add startup validation and PDF browser runtime documentation.

## 2. Article Archiving

- [x] 2.1 Implement public CSDN URL validation and compatible HTTPS page fetching.
- [x] 2.2 Extract article metadata and正文内容 while excluding non-body content.
- [x] 2.3 Preserve code comments, whitespace, line breaks, indentation, and box-drawing characters.
- [x] 2.4 Download body resources into `assets/` and rewrite HTML references.
- [x] 2.5 Generate HTML and optional PDF with partial-result handling.
- [x] 2.6 Implement domain/article-key layout, metadata JSON, overwrite behavior, and safe staging replacement.

## 3. Local Search and File List

- [x] 3.1 Implement SQLite metadata indexing and fuzzy metadata search.
- [x] 3.2 Add the homepage downloaded-file list ordered by latest save time.
- [x] 3.3 Add HTML/PDF fallback links and empty-state handling.
- [x] 3.4 Add controlled local-file routes.

## 4. Verification and Documentation

- [x] 4.1 Add parser, fetcher, resource, output, storage, and Web regression tests.
- [x] 4.2 Run the full test suite and OpenSpec validation.
- [x] 4.3 Consolidate the first-phase requirement into one main spec and this archive directory.
- [x] 4.4 Maintain open-source README, project requirements, handoff notes, and OpenSpec guidance.
