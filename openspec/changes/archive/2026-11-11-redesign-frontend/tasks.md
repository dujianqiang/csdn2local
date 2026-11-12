## 1. Shared frontend foundation

- [x] 1.1 Add FastAPI static asset mounting and a shared Jinja base template without changing existing route or form contracts.
- [x] 1.2 Add the archive-workbench design tokens, typography, layout primitives, form controls, status styles, focus states, responsive rules, and reduced-motion rules in shared CSS.

## 2. Download and library pages

- [x] 2.1 Redesign the single-article download page with the archive-workbench hero, URL capture form, format controls, search area, result rows, and useful empty state.
- [x] 2.2 Redesign the topic download page with grouped URL, concurrency, and output-format controls plus validation and active-job feedback.
- [x] 2.3 Redesign the single-article result page for success, partial success, failure, retry, output links, and warnings.

## 3. Topic progress and result states

- [x] 3.1 Redesign the topic progress page with stage messaging, progress counts, failure count, elapsed time, and automatic refresh explanation.
- [x] 3.2 Redesign the topic result page with success, partial-success, failure, retry, output link, and per-article processing results.

## 4. Verification and polish

- [x] 4.1 Update or extend Web tests so the redesigned pages retain navigation, form fields, status text, links, retry behavior, and empty/error states.
- [x] 4.2 Run the test suite and start the local app to review desktop and narrow-screen rendering; fix any accessibility, overflow, or selector-specificity issues found in the visual pass.
- [x] 4.3 Validate the completed change against OpenSpec and confirm all implementation tasks are complete before archiving.
