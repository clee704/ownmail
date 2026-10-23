---
id: TASK-152
title: Close explicitly managed SQLite handles on every exit path
status: To Do
assignee: []
created_date: '2026-10-23 06:53'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The TASK-151 ownership audit found remaining cleanup gaps outside request-scoped transaction contexts. Archive download and rebuild batches execute PRAGMA setup before their cleanup try blocks, and several archive/command finally blocks call commit before close, so setup or commit errors can skip connection closure and signal-handler restoration. Maintenance scripts also have raw transaction contexts or close only after successful queries. Preserve transaction and resumability behavior while making owned-handle cleanup unconditional.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owned batch handles close and temporary signal handlers are restored when setup or final commits raise; caller-owned handles retain their ownership.
- [ ] #2 Maintenance script handles close on success and query failures.
- [ ] #3 Synthetic failure-injection regressions verify cleanup and preserve batch transaction behavior.
- [ ] #4 The full pre-push gate passes and the fix is committed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Audit locations: ownmail/archive.py download batch setup/finally, _register_and_index, register_scanned_email, and scanned-file batching; ownmail/commands.py rebuild, date population, and label-sidecar batches; scripts/repair_labels.py repair context; scripts/audit_encoding.py query/fetch cleanup.
<!-- SECTION:NOTES:END -->
