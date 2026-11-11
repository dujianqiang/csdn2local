## 1. Compatible Page Fetching

- [x] 1.1 Replace the CSDN page request with standard-library HTTPS fetching while preserving redirects, status, charset, and final URL handling.
- [x] 1.2 Map HTTP, TLS, DNS, timeout, and connection failures to readable archive errors.
- [x] 1.3 Add regression tests for successful fetches, HTTP failures, and explicit access messages without external network calls.

## 2. Verification

- [x] 2.1 Run the full test suite and OpenSpec strict validation.
- [x] 2.2 Verify the user-provided URL can be fetched and archived after restarting the service.
