---
id: TASK-115
title: Remove the unused query helpers from ArchiveDatabase
status: To Do
assignee: []
created_date: '2026-09-27 08:03'
labels:
  - search
dependencies: []
priority: low
ordinal: 26500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ArchiveDatabase._parse_query and _convert_query (ownmail/database.py) predate ownmail/query.py. search() parses with query.parse_query, and nothing outside tests/test_fixtures.py calls either helper, so their tests cover code no user path runs.

search() also sets distinct = "" in both paths under a comment that describes a decision the code no longer makes.

Found while fixing TASK-22.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _parse_query and _convert_query are deleted along with their tests
- [ ] #2 search() no longer carries the constant distinct placeholder
- [ ] #3 The pre-push gate passes
<!-- AC:END -->
