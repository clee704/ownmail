---
id: TASK-127
title: Reconcile sanitizer install safety with strict dependency validation
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-30 06:34'
labels:
  - sanitizer
  - reliability
dependencies:
  - TASK-118
  - TASK-40
priority: high
type: bug
ordinal: 9850
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Local and upstream histories contain complementary sanitizer fixes. Preserve upstream process locking, recheck under the lock, interrupted-install markers and cleanup, development-dependency preservation, detailed errors and worker restarts without npm installs. Retain local strict manifest/version validation, pipx repair guidance and completed body/charset behavior. Produce a tested local reconciliation candidate without changing default-branch production code or publishing. Historical TASK-118 and TASK-40 remain completed records; this task owns only the bounded reconciliation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The local candidate preserves both histories, upstream sanitizer concurrency/interruption/restart behavior, and local strict handling of empty or malformed dependency maps, null requirements and invalid leading-zero versions.
- [ ] #2 Early server refusal preserves upstream failure details and local pipx/source repair guidance; retained startup and dependency regressions pass without weakening assertions.
- [ ] #3 Local TASK-40 body/charset behavior and TASK-126 remain intact; upstream setup/ignore documentation and TASK-121 through TASK-125/execution-order records are retained. TASK-116 and active TASK-16 remain separate.
- [ ] #4 Focused retained-behavior tests, required browser coverage, Ruff check and format-check, deptry, and the full pre-push coverage gate pass in private runtime state; independent Astra Ultra review has no unresolved findings.
- [ ] #5 The candidate and task closure are committed locally with normal hooks, the candidate working tree is clean, and an exact integration recommendation is supplied; no default-branch code update or publication occurs.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Verify clean master at 705aa580b8c0b14905471942918834115329d533 and upstream fd7f8af0810ab273310947e46b5e8f88c3fb9e8f, with common ancestor 654e88c2836e1426732b46b87ec8fa5ea3ced40c. Inspect both diffs and commit this task-only checkpoint before implementation.
2. Relinquish the narrow main lease after the claim commit. Create an isolated reconciliation branch/worktree from that checkpoint, preserving existing branches/worktrees. Merge the fixed upstream history only there; stop for unrelated conflicts or product/security decisions.
3. Resolve documented sanitizer/startup/test/docs overlap by retaining upstream install safety and adding local strict validation and pipx guidance. Keep local charset work and all historical/follow-up records. Update the execution-order record for this explicit reconciliation assignment only on the candidate.
4. Use a source-bound environment and private cache/temp/browser state. Run focused union regressions, explicit lint/format/dependency checks and one full required headless pre-push coverage gate. Obtain independent Astra Ultra review of the complete reconciliation and resolve substantiated findings.
5. Record verified criteria and a tested clean local candidate with normal hooks. Supply ancestry, validation and exact later-integration guidance; do not alter main production code or publish.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise: the histories diverge at 654e88c2836e1426732b46b87ec8fa5ea3ced40c. Neither subsumes the other: upstream adds install locking/recovery while local work adds strict validation and body decoding fixes. Reconciliation retains both before authorized upstream delivery. Review bases: local 705aa580b8c0b14905471942918834115329d533 and upstream fd7f8af0810ab273310947e46b5e8f88c3fb9e8f. The main lease permits only this new task/claim checkpoint. No schema, credential, dependency-version, real-mail, GUI, force/reset/discard or publishing scope is granted. Astra Ultra advisory comparison confirms the bounded adaptation; final independent review will use a separate reviewer. Task creation uses the approved temporary Backlog-only offline setting, restored byte-for-byte afterward; Git remote/security settings and hooks remain unchanged.
Next action: commit this task-only plan with normal hooks, release the main lease, and create the isolated reconciliation candidate from that checkpoint.
<!-- SECTION:NOTES:END -->
