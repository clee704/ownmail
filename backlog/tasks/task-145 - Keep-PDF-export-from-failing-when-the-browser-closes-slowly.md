---
id: TASK-145
title: Keep PDF export from failing when the browser closes slowly
status: Done
assignee: []
created_date: '2026-10-11 22:58'
updated_date: '2026-10-11 23:26'
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
- [x] #1 A context or browser close that exceeds its deadline after the PDFs are written does not fail the export
- [x] #2 Browser processes left by a slow close are still stopped within a bounded time
- [x] #3 A test reproduces a slow close deterministically, without relying on machine load, and fails before the fix
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The renderer now ignores a context.close() or browser.close() that overruns its 5s deadline (closeWithin). A close only releases resources, and a render failure (including the 45s render deadline) already propagates from the try block, so ignoring close errors never hides a failure before a PDF is written. A slow per-message context close lets the run continue with the next message; if the browser is wedged, the next render hits its own deadline. Security settings are unchanged.

Process cleanup: pdf_export.py only signals the renderer's process group when the renderer times out or is interrupted, and Playwright launches Chromium detached in its own group, so that cleanup never reached a slow-closing browser after a normal renderer exit. The renderer now calls process.exit() when main settles; Playwright's exit handler then SIGKILLs the browser's process group of any browser not yet closed. Without the explicit exit, the open browser pipe kept Node alive until the close finished.

Test: test_actual_renderer_does_not_execute_unsanitized_page_scripts gains a POSIX slow_close variant. OWNMAIL_BROWSER_EXECUTABLE points at a shell wrapper that runs the real Chromium and then execs sleep 60, so browser.close() cannot finish within its deadline. The test asserts the PDF is produced and the wrapper is gone within 2s of renderer exit. It failed with 'PDF rendering timed out' against the previous renderer. Caveat: the liveness check treats a zombie as running; a minimal container init that never reaps orphans could make it fail.
<!-- SECTION:NOTES:END -->
