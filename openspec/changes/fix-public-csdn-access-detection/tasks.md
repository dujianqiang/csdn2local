## 1. Access Detection Fix

- [x] 1.1 Remove the page-wide generic paid-content marker and retain only explicit login/paid access signals.
- [x] 1.2 Add a regression test for a public page containing a hidden generic recharge component.
- [x] 1.3 Add a regression test confirming explicit login redirects and access messages remain rejected.

## 2. Verification

- [x] 2.1 Run the full test suite and OpenSpec strict validation.
- [x] 2.2 Re-run the user-provided CSDN URL through the archive flow and verify the saved HTML output.
