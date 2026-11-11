## 1. Index Query

- [x] 1.1 Add an ArticleIndex query that returns all indexed articles ordered by `saved_at` descending.
- [x] 1.2 Reuse the existing archive-file selection logic so each result resolves to local HTML first and PDF second, without exposing filesystem paths.

## 2. Home Page

- [x] 2.1 Update the home route to load all downloaded articles when the search keyword is empty and filtered results otherwise.
- [x] 2.2 Update the home template to show the downloaded-file list with article title and local address only.
- [x] 2.3 Add separate headings and empty-state messages for the full list and no-match search results.

## 3. Verification

- [x] 3.1 Add index tests covering newest-first ordering, empty index results, and HTML/PDF file fallback.
- [x] 3.2 Add Web tests covering the default downloaded-file list, keyword filtering, empty state, and local links.
- [x] 3.3 Run OpenSpec validation and the full test suite, then update the handoff documentation if needed.
