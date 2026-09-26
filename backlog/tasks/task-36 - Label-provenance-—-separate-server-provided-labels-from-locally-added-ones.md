---
id: TASK-36
title: Reassess label provenance for explicit repairs
status: To Do
assignee: []
created_date: '2026-08-06 18:38'
updated_date: '2026-09-26 02:24'
labels: []
dependencies: []
priority: low
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reassess label provenance only for a concrete explicit-repair use case under
[Owning your mail](../../docs/philosophy.md). It is not a prerequisite for local
label editing (TASK-5.4) or the ownership design.

The earlier proposal would replace a server-origin label partition whenever
the server was re-read. That conflicts with the clarified ownership boundary:
all captured labels become ownmail's, including labels originally supplied by
the server. Routine download, Active refresh, and cleanup must leave that
snapshot and subsequent local edits alone.

Origin metadata could help explain or preview an operator-requested repair,
but that benefit must be demonstrated before adding storage and migration
cost. Provenance alone never authorizes a server refresh to replace labels or
restore labels the user removed locally. If no concrete need remains, close
this as a decision without adding provenance storage.

Any implementation that changes the database schema follows the existing
repository approval and PR requirements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A concrete explicit-repair use case and its benefit are recorded before implementation, or the task is closed with a decision that provenance is unnecessary.
- [ ] #2 Any retained provenance design preserves all captured and locally edited labels during routine operations, including intentional removals; it introduces no automatic server-partition replacement.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: candidate concrete use for AC 1 is relabel. Its union strategy can re-add a folder label the user removed locally, and its server strategy drops local edits; origin metadata could separate those cases. Without such a use, close as unnecessary.
<!-- SECTION:NOTES:END -->
