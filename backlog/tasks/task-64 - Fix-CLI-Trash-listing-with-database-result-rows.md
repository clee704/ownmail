---
id: TASK-64
title: Fix CLI Trash listing with database result rows
status: To Do
assignee: []
created_date: '2026-09-13 08:07'
labels:
  - cli
dependencies: []
type: bug
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The trash command unpacks six values from get_trashed_emails, although the database returns additional date and snippet fields (and now an attachment flag). Listing a nonempty Trash raises ValueError. This predates TASK-63; existing CLI tests hide it by supplying six-field mock rows. Reproduced with a temporary synthetic database.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The trash command lists a nonempty Trash using rows returned by ArchiveDatabase, including the correct trash date, sender, and subject.
- [ ] #2 A regression test uses the real database row shape and fails against the old unpacking.
<!-- AC:END -->
