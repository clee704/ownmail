---
id: TASK-5.4
title: Local label editing in the web UI
status: To Do
assignee: []
created_date: '2026-07-25 07:04'
updated_date: '2026-09-14 09:07'
labels: []
milestone: m-3
dependencies: []
parent_task_id: TASK-5
priority: medium
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement archived label editing under [Owning your mail](../../docs/philosophy.md).
Captured labels belong to ownmail regardless of where they originated. Adding
or removing them locally must never update a server copy or change capture or
cleanup eligibility.

Write labels atomically to the existing sidecar, with the database updated as
a rebuildable index. Reuse the existing sidecar and label helpers. An empty
label list is an intentional local state, not missing metadata to fetch again.
If indexing fails after a durable sidecar write, recovery must preserve the
sidecar's labels.

Only owned archive copies can receive local label edits. An Active-only message
has no local archive labels to edit. If an archived message also has an Active
server copy, edits apply solely to the archived copy. Live work remains in the
mail client.

TASK-20 already made update-labels prefer existing sidecars; its original
failure is fixed. Preserve that behavior, including intentional empty labels,
through download, Active refresh, rebuild, and cleanup. Server changes cannot
silently restore removed labels. Explicit operator-requested repair remains a
separate operation; do not invoke relabel automatically.

TASK-19's optional label visibility filter and TASK-36's optional provenance
work are not prerequisites. If label visibility filtering exists when this
lands, explain any hidden label instead of making an edit disappear silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Labels can be added and removed on an archived message from the web UI without changing any server copy.
- [ ] #2 The sidecar is the atomic durable write target; the database is the derived index, and failed or interrupted edits preserve a recoverable authoritative label set.
- [ ] #3 A locally edited label set, including an intentionally empty one, survives download, update-labels, rebuild, and rebuild --only sidecars unchanged.
- [ ] #4 Active-only messages reject local label edits; a message with both an archived copy and Active server state edits only its archive copy.
- [ ] #5 Active refresh and cleanup do not replace archived labels or restore locally removed ones, and server role or label changes do not alter them.
<!-- AC:END -->
