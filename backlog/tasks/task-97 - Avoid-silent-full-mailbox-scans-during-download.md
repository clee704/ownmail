---
id: TASK-97
title: Avoid silent full-mailbox scans during download
status: To Do
assignee: []
created_date: '2026-09-21 03:16'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 99000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Terminal downloads can appear hung after authentication and the previously downloaded total. TASK-28 routes every CLI download through sync_live, which waits for a complete live snapshot before capturing or refreshing messages. Gmail enumeration sends a separate synchronous metadata request for every visible message, including Spam and Trash, on every run. It emits no terminal progress and bypasses the earlier incremental download path. IMAP enumeration also fetches metadata one UID at a time. Preserve current-state ownership checks while reducing repeated request work and reporting scan progress.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Live enumeration reports bounded terminal and web progress before capture begins, including when no messages have been saved.
- [ ] #2 Gmail live enumeration avoids one separate HTTP round trip per visible message; synthetic request-count checks cover initial and unchanged repeat runs.
- [ ] #3 Any batching or incremental optimization preserves complete lifecycle observations, account scope, and safe handling of partial responses and interruptions.
- [ ] #4 Tests reproduce the former silent scan and verify the chosen behavior without real accounts; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Diagnosed against the installed editable source at 2035a56. Terminal history from a real archive showed successful Gmail authentication, silence after the archived total, and zero captures before interruption. A synthetic 1000-message mailbox required two list requests and 1000 serial minimal GETs on each of two runs, with zero stdout characters; the first content read occurred only after all metadata requests. No stack from the interrupted process survives, so an additional network stall in that specific attempt remains unverified. The routing and enumeration were introduced in 8657a68. No runtime behavior changed during diagnosis.
<!-- SECTION:NOTES:END -->
