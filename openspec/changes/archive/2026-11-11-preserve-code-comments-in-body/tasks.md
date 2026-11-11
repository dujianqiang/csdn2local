## 1. Parser Fix

- [x] 1.1 Replace broad comment-class removal selectors with precise comment-container selectors.
- [x] 1.2 Add a regression fixture proving `span.token.comment` inside code is preserved while a real comment container is removed.

## 2. Verification

- [x] 2.1 Run the full test suite and OpenSpec strict validation.
- [x] 2.2 Re-download the user-provided CSDN article and verify code-comment text is present in the saved HTML.
