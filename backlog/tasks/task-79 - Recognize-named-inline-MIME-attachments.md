---
id: TASK-79
title: Recognize named inline MIME attachments
status: In Progress
assignee: []
created_date: '2026-09-14 04:06'
updated_date: '2026-09-14 04:11'
labels: []
dependencies: []
type: bug
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Named MIME parts marked inline are omitted from the message attachment list, download route, and indexed attachment names. Confirmed against a real archive containing a named PDF with inline disposition. Use consistent attachment classification across these paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Named inline parts and named parts without a disposition appear in the attachment list and can be previewed or downloaded with the correct bytes.
- [x] #2 The parser records these filenames for attachment indexing while retaining explicit attachment support.
- [x] #3 Synthetic regressions fail against the previous detection logic, and full pre-push checks pass.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Share MIME attachment classification between the parser and both web routes. Preserve body extraction for named inline text. Extend synthetic tests for filename fallbacks, downloaded bytes, and attachment URL order; verify the reported message through the running server and run full pre-push checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The parser and both web routes share attachment classification for explicit attachment dispositions and filename-bearing parts. Named inline text remains visible in the body, and CID images still render. The reported message now lists its PDF; preview and download responses match the original decoded bytes. Existing indexed attachment flags require an operator-run index rebuild. Separate embedded-message traversal and serialization defects are tracked in TASK-80.

Synthetic detection regressions produced 10 failures against the previous code. Parser and web tests pass (488 passed, 1 expected failure). Isolated in-memory mutations made the three new body/CID preservation cases fail as intended while the unnamed CID control passed. Independent review verified mixed attachment ordering, exact download payloads, preview security headers, and malformed filename tolerance.

Full pre-push hooks passed, including ruff, deptry, and the complete test suite with the coverage gate.
<!-- SECTION:NOTES:END -->
