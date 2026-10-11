---
id: TASK-145
title: Keep PDF export from failing when the browser closes slowly
status: To Do
assignee: []
created_date: '2026-10-11 22:58'
labels:
  - pdf
dependencies: []
priority: medium
type: bug
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ownmail/pdf_renderer.js wraps context.close() and browser.close() in 5-second deadlines. Under heavy CPU load the close can take longer after the PDF is already written; the renderer then exits 1 and export reports "PDF rendering timed out". Running the suite in parallel (TASK-143) made tests/test_pdf_export.py::test_actual_pdfs_are_readable_and_block_untrusted_resources and ::test_actual_renderer_does_not_execute_unsanitized_page_scripts fail intermittently; instrumentation traced it to the browser.close() deadline.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A context or browser close that exceeds its deadline after the PDFs are written does not fail the export
- [ ] #2 Browser processes left by a slow close are still stopped within a bounded time
- [ ] #3 A test reproduces a slow close deterministically, without relying on machine load, and fails before the fix
<!-- AC:END -->
