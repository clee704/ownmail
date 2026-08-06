---
id: TASK-34
title: 'IMAP download fails on iCloud: RFC822 fetch returns no data'
status: Done
assignee: []
created_date: '2026-08-06 03:53'
updated_date: '2026-08-06 03:53'
labels: []
dependencies: []
priority: high
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`download` errored on every message from an iCloud IMAP source with "No data for UID <n>".

Two independent bugs in `providers/imap.py`, both affecting iCloud IMAP responses:

1. **RFC822 fetch returns nothing.** `UID FETCH n (RFC822)` on imap.mail.me.com answers `OK` with a bare `* 1 FETCH (UID 194)` — no literal, no message data. Every download failed. `(BODY.PEEK[])` returns the message normally. BODY.PEEK also keeps \\Seen off in its own right, so the read-only SELECT is no longer the only thing protecting the user's mailbox.

2. **Message-ID map keyed by sequence number.** `_get_message_ids_for_uids` matched `(\d+) \(` — the leading sequence number — while its callers look results up by UID. On any mailbox where seq != uid (i.e. any mailbox with deletions) the map returned another message's Message-ID or nothing, so cross-folder dedup and label mapping were both wrong. Same class of mistake as commit 7089952, which fixed it only in the download path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 IMAP download handles iCloud IMAP responses
- [x] #2 Fetch spec is BODY.PEEK[] in both the single and batch download paths, pinned by a test
- [x] #3 _get_message_ids_for_uids returns a map keyed by UID, pinned by a test
- [x] #4 Test mocks reflect real UID FETCH responses (implicit UID present)
- [x] #5 pre-commit run -a --hook-stage pre-push passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Response inspection identified two details relevant to the fix:

- iCloud returns the messages of a batched UID FETCH out of order, so parsing by position would silently mis-file messages. The batch parser keys on UID, which is correct; a comment now says why.
- The old test mocks for header fetches omitted the implicit UID that RFC 3501 6.4.8 requires a server to include in any UID FETCH response, which is why the seq-vs-UID bug survived. The mocks now carry it.

`test_maps_uids_to_message_ids` asserted the seq-keyed result — it encoded the bug, contradicting both the function's docstring and its callers. Expectation corrected rather than the code loosened.

Fixing bug 2 changes what a standard-IMAP scan returns: real duplicates are now detected, so the download list shrinks and labels land on the right messages. Existing IMAP archives scanned before this fix have wrong cross-folder labels — TASK-20 territory.

No migration or state cleanup needed for the reported failure: download failures live in an in-memory list, and sync state only advances on an error-free run, so re-running download resumes cleanly.
<!-- SECTION:NOTES:END -->
