---
id: TASK-144
title: Fix label editor browser tests under WebKit
status: In Progress
assignee:
  - codex
created_date: '2026-10-11 22:46'
updated_date: '2026-10-21 06:41'
labels:
  - testing
dependencies: []
priority: low
ordinal: 26950
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With OWNMAIL_BROWSER_ENGINE=webkit, four tests in tests/test_label_editor.py fail on page errors (test_cached_message_markup_cannot_send_label_requests[page] and [injected-editor-script], test_editor_ignores_message_markup_when_its_own_section_is_missing, test_archive_editor_saves_its_own_labels_beside_message_markup). They pass under Chromium. Found while working on TASK-143; the failures predate it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All label-editor browser tests pass with WebKit and Chromium, with browser tests required.
- [x] #2 The forged-message cases still detect label requests and loading-overlay changes, and unexpected page errors still fail the tests.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: a702211d9549b1903f2e7e696febc7e8faf706e4.
1. Reproduce the four reported WebKit failures and identify their source.
2. Make the smallest correction while retaining the label-request, loading-overlay, and page-error assertions. Scope excludes threading, storage changes, and unrelated browser failures.
3. Run the label-editor tests in WebKit and Chromium, prove the affected assertions reject broken behavior, review the full task diff, and pass the required pre-push gate before closure.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Selected because doc-4 omits TASK-144. Place it with the test-reliability fixes before conversation grouping, whose storage changes need separate sign-off.

Reproduced all four failures against the review base. Each failure comes from WebKit fetching GET /manifest.webmanifest, which the shared served_files helper omitted from the declared page assets. No page-error failure was observed in this reproduction. Include the manifest through that helper and preserve the existing request and page-error assertions.

Focused validation: OWNMAIL_REQUIRE_BROWSER_TESTS=1 with OWNMAIL_BROWSER_ENGINE=webkit passed all 17 label-editor tests and all 37 email-contrast tests; Chromium passed the same 54 tests. Three temporary in-memory test mutations injected a label request, a visible loading overlay, and an unexpected page error; each failed its existing assertion. Self-review against the recorded base found no further issue; no production behavior or request expectations changed.
<!-- SECTION:NOTES:END -->
