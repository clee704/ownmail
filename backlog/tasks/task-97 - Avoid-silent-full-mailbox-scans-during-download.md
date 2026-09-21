---
id: TASK-97
title: Avoid silent full-mailbox scans during download
status: In Progress
assignee: []
created_date: '2026-09-21 03:16'
updated_date: '2026-09-21 03:37'
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
- [x] #1 Live enumeration reports bounded terminal and web progress before capture begins, including when no messages have been saved.
- [x] #2 Gmail live enumeration avoids one separate HTTP round trip per visible message; synthetic request-count checks cover initial and unchanged repeat runs.
- [x] #3 Any batching or incremental optimization preserves complete lifecycle observations, account scope, and safe handling of partial responses and interruptions.
- [x] #4 Tests reproduce the former silent scan and verify the chosen behavior without real accounts; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: a970885e4776c283d2faa0ea90b3bcd3ea71f22b. Batch fresh Gmail lifecycle metadata reads without changing capture, account, OAuth, or index semantics. Add bounded terminal and web scan progress to Gmail and IMAP enumeration before capture. Verify synthetic initial/repeat request counts, partial responses, interruptions, lifecycle transitions, and progress privacy; run the full pre-push gate and review the complete task diff before committing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Diagnosed against the installed editable source at 2035a56. Terminal history from a real archive showed successful Gmail authentication, silence after the archived total, and zero captures before interruption. A synthetic 1000-message mailbox required two list requests and 1000 serial minimal GETs on each of two runs, with zero stdout characters; the first content read occurred only after all metadata requests. No stack from the interrupted process survives, so an additional network stall in that specific attempt remains unverified. The routing and enumeration were introduced in 8657a68. No runtime behavior changed during diagnosis.

Implemented fresh Gmail metadata batches of 50 and one label catalog per scan. A synthetic 1000-message mailbox using the real Google API client HTTP boundary takes 23 round trips on both initial and unchanged repeat scans: one catalog, two list pages, and twenty batches. Inner requests still consume Gmail quota. The batch size follows the Gmail batching guide: https://developers.google.com/workspace/gmail/api/guides/batch. Lifecycle roles are reread every run, including Spam and Trash; no persistent cursor or schema change is needed. Terminal scan updates are limited to one per second, with immediate start/completion lines; web counts use the existing 250ms write throttle and reset per source. IMAP reports each metadata check, including duplicates and failures. Synthetic tests verify pre-capture visibility through the real subprocess/status endpoint and Chromium UI, conservative partial responses, account/source scope, and interruption retention. Deliberate mutations to batching, completeness, progress counters, validation, terminal throttling, and UI rendering failed the intended tests.

Validation: 3489 tests passed, one expected failure, and 96.32% branch-inclusive coverage with required browser tests enabled. The complete pre-push gate passed after staging was fixed in place. Independent GPT review found no actionable issues; the second review is pending.
<!-- SECTION:NOTES:END -->
