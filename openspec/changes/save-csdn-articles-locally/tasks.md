## 1. Project Setup

- [x] 1.1 Initialize the Python Web service project and dependency configuration for FastAPI, HTTP fetching, HTML parsing, templating, SQLite access, and PDF rendering.
- [x] 1.2 Create the application module structure, configuration loading, `data/` directory handling, and local development entrypoint.
- [x] 1.3 Add startup validation and documentation for the required PDF browser runtime.

## 2. Archive Storage and Metadata

- [x] 2.1 Define the article metadata model and JSON serialization for title, author, publication time, tags, original URL, save time, formats, and warnings.
- [x] 2.2 Implement domain directory creation, article ID plus sanitized-title naming, Windows-safe filename normalization, length limits, and a stable fallback when no article ID is available.
- [x] 2.3 Implement staging-directory writes and safe replacement of an existing article archive only after at least one selected output is ready.
- [x] 2.4 Implement the SQLite metadata index, schema initialization, URL upsert behavior, and cleanup/update behavior when an archive is overwritten.

## 3. CSDN Fetching and Body Extraction

- [x] 3.1 Implement URL validation and public-page fetching with clear errors for invalid, inaccessible, login-required, or paid pages.
- [x] 3.2 Build metadata extraction for title, article ID, author, publication time, tags, and canonical/original URL.
- [x] 3.3 Build and test CSDN body extraction using representative public-page fixtures, excluding comments, advertisements, recommendations, sidebars, and other non-body nodes.
- [x] 3.4 Implement body HTML normalization while preserving text, code blocks, images, and required formatting.
- [x] 3.5 Implement best-effort body-resource downloading into `assets/`, relative URL rewriting, missing-resource collection, and partial-result warnings.

## 4. Output Generation and Result Handling

- [x] 4.1 Implement offline HTML generation from the normalized article body and local relative assets.
- [x] 4.2 Implement optional PDF generation from the normalized local HTML using the configured browser runtime.
- [x] 4.3 Implement synchronous archive orchestration for default HTML, HTML-only, PDF-only, and HTML-plus-PDF selections.
- [x] 4.4 Implement complete, partial, and failed result states with specific reasons, warnings, and retry parameters.

## 5. Web Interface and Search

- [x] 5.1 Implement the single-URL archive form with HTML as the default format and optional PDF/HTML format selection.
- [x] 5.2 Implement synchronous progress/result rendering, partial-resource warnings, format-specific errors, and retry for the same URL and formats.
- [x] 5.3 Implement the single keyword search entry with fuzzy matching over title, domain, original URL, author, and tags, without body full-text search.
- [x] 5.4 Implement search results that display only title and a local address, preferring HTML and falling back to PDF when HTML is absent.
- [x] 5.5 Add controlled local-file routes so search links cannot expose arbitrary filesystem paths.

## 6. Verification

- [x] 6.1 Add unit tests for URL normalization, metadata extraction, article-key generation, filename sanitization, storage layout, and overwrite behavior.
- [x] 6.2 Add parser fixture tests proving body-only extraction and preservation of code, images, and formatting.
- [x] 6.3 Add resource and output failure tests proving partial archives retain successful files and report missing outputs.
- [x] 6.4 Add Web/API integration tests for synchronous archive submission, format selection, retry, metadata search, and HTML/PDF link fallback.
- [x] 6.5 Run OpenSpec validation and the full test suite, then update the project documentation with local startup and usage instructions.
