---
id: TASK-109
title: Keep Active mail current through partial refreshes
status: Done
assignee: []
created_date: '2026-09-22 05:44'
updated_date: '2026-09-22 05:55'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 110000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A live report exposed stale Active entries after an incomplete provider listing and repeated full IMAP history reads when an empty filtered search is returned without SEARCH data. Verify the provider response, bound the repeat scan, and apply independently confirmed message state even when unrelated observations fail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Empty IMAP filtered-search responses avoid repeated historical downloads without accepting unverified arrival or identity searches.
- [x] #2 Individually confirmed cached-message transitions are applied during partial refreshes; failed or changed identities retain their cache.
- [x] #3 Synthetic regressions and mutation checks pass, the full pre-push gate passes, and live behavior is verified before committing.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review base f9e8a73. Implement in an isolated checkout so development does not interrupt the running download. Keep archive schema, credentials, OAuth and owned message files unchanged.

Confirmed an IMAP server returns only tagged OK for empty filtered searches. Keep the existing full-metadata fallback, but omit eligible identities at or below a completed UIDVALIDITY-scoped watermark unless they remain pending. This preserves fresh state checks and eliminates repeated legacy body reads. A read-only live scan verified the reduced candidate set. Partial source listings now permit individually scoped cache reconciliation; confirmed absent/discarded entries retire immediately while lookup failures and identity mismatches retain their copies. Updated prior tests whose blanket retention and historical-body expectations caused the reported defects; metadata validation and failure-retention assertions remain. The original implementation fails the new regressions. Targeted provider, cache, lifecycle and scope tests pass. Gmail member HTTP 429 retry is recorded separately in TASK-110.

Completed in 0c0759e. The final stable-tree pre-push gate passed with browser tests required: 3,810 passed, one expected failure, 96.37% branch-inclusive coverage. The pending-identity regression rejects a mutation that drops its checkpoint guard. Live verification confirmed a successful, much shorter download, successful new captures, retirement of stale Active entries, and current checks for every remaining Active row. Settings reports the downloader stopped. Gmail throttling still leaves the source-wide completeness warning; TASK-110 tracks bounded retries. No archive schema, credentials, OAuth, dependency or owned-file deletion behavior changed.
<!-- SECTION:NOTES:END -->
