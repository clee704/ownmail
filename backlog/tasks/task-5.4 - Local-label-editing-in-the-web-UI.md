---
id: TASK-5.4
title: Local label editing in the web UI
status: In Progress
assignee: []
created_date: '2026-07-25 07:04'
updated_date: '2026-09-14 21:39'
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
- [x] #1 Labels can be added and removed on an archived message from the web UI without changing any server copy.
- [x] #2 The sidecar is the atomic durable write target; the database is the derived index, and failed or interrupted edits preserve a recoverable authoritative label set.
- [x] #3 A locally edited label set, including an intentionally empty one, survives download, update-labels, rebuild, and rebuild --only sidecars unchanged.
- [ ] #4 Active-only messages reject local label edits; a message with both an archived copy and Active server state edits only its archive copy.
- [ ] #5 Active refresh and cleanup do not replace archived labels or restore locally removed ones, and server role or label changes do not alter them.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement a raw local-label editor for existing owned messages. Sidecars are read first and written atomically with other metadata preserved; reuse one database label-replacement helper. Report durable save separately from index failure. Add GET/POST endpoints under existing CSRF protection, reader controls and feedback, and focused persistence/recovery/browser tests. Active and cleanup lifecycle integration criteria remain open until TASK-28 and TASK-14.2 exist.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Continuing the independent fallback after TASK-90 completion and a reviewed TASK-38 checkpoint. TASK-28 awaits storage approval; TASK-38 broad clearance remains blocked on provider-state evidence; TASK-14.2 depends on those tasks and explicit cleanup/OAuth approvals. This implementation changes only owned label sidecars and their existing derived index; no schema change, archive message movement, or server mutation.

Implemented the owned-message label editor and GET/POST label endpoints. Atomic sidecar writes preserve all other metadata and exact label text; intentional empty labels persist. The existing database label replacement helper is shared by editing and rebuild/backfill paths. Saved labels remain authoritative after indexing failures, with explicit UI feedback and retry. Backend tests cover preservation through download, update-labels, rebuild, and rebuild --only sidecars, plus interruption and write failures. Route tests verify server isolation and CSRF behavior. Twelve real Chromium scenarios cover editing, validation, pending/failure/retry states, stale loading responses, and mobile layout; the mobile rendering was visually checked. Independent review identified an internal .eml-alias sidecar mismatch; a scan/rebuild regression reproduced it and now passes with the tracked sidecar path preserved. Isolated mutations rejected lost metadata, skipped empty-label indexing, swallowed interruption, unsafe sidecars, unsafe HTML label rendering, and stale loading responses. ACs #4 and #5 remain open: unknown IDs already reject edits, but actual Active-only, dual-state, refresh, and cleanup integration must be verified after TASK-28 and TASK-14.2 exist. Next action: complete those dependencies and run the lifecycle integration cases before marking this task Done.

Implementation commit: 371855b. The alias-sidecar fix passed independent verification. Final pre-commit run -a --hook-stage pre-push passed with OWNMAIL_REQUIRE_BROWSER_TESTS=1; total branch coverage 95.97%. Owned-label editing is delivered. Keep this task In Progress until ACs #4 and #5 are verified against the actual Active and cleanup implementations.
<!-- SECTION:NOTES:END -->
