---
id: TASK-78
title: Correct per-account archived totals after duplicate downloads
status: To Do
assignee: []
created_date: '2026-09-14 03:58'
labels: []
dependencies: []
type: bug
ordinal: 82000
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
