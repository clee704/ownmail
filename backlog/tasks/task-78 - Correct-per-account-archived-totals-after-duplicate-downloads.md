---
id: TASK-78
title: Correct per-account archived totals after duplicate downloads
status: To Do
assignee: []
created_date: '2026-09-14 03:58'
updated_date: '2026-09-26 02:24'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The per-account download summary adds backup success_count to the prior archive count, but success_count also includes content-dedup skips. The summary can therefore overstate archived messages. Read the final account count when reporting archive size.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-account archived totals equal the stored message count after a download containing content duplicates.
- [ ] #2 A regression test covers successful downloads that do not add archive rows.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: affects the default EmailArchive.backup path only. The overall summary already reads the database count; the per-account 'Total' and 'Downloaded' lines in cli.py still add success_count, which includes content-duplicate skips.
<!-- SECTION:NOTES:END -->
