---
id: TASK-37
title: update-labels --source silently processes only one source
status: In Progress
assignee:
  - Ownmail backend IC
created_date: '2026-08-06 19:22'
updated_date: '2026-09-30 16:50'
labels: []
dependencies: []
priority: medium
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`update-labels --source` advertises `(default: all sources)` in its help, but
`cmd_update_labels` falls through to `sources[0]` when no source is named and
processes exactly that one. Found while making `relabel --source` optional
(TASK-35).

## Effect

A user with more than one source who runs a bare `update-labels` gets the
backfill for whichever source happens to be first in `config.yaml`, and no
indication the others were skipped. The output names the source it picked, so
the evidence is there, but nothing says the run was partial — and the help text
states the opposite.

Worse for the second source than a plain no-op: `update-labels` is the repair
for archives captured before sidecars existed, so the sources it silently skips
are left with emails carrying no labels at all, which is exactly the state the
command exists to fix.

## Fix

Loop over every source when none is named, the way `download` and `reset-sync`
already do. The per-source dispatch on `source_type` is already in place; only
the selection above it assumes a single source.

Worth checking the same pattern elsewhere while in there — the "first source"
fallback may have been copied.

## Acceptance criteria

- A bare `update-labels` with several configured sources backfills all of them
- Named `--source` still restricts to that one
- Help text and behaviour agree
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Bare update-labels and sync-check process every configured source in order, retaining per-source output and continuing past empty or unsupported sources.
- [ ] #2 A named source still selects only that source; missing and unknown-source handling and advertised all-source help remain consistent.
- [ ] #3 During a bare update-labels sweep, accountless legacy rows are eligible only for the original first configured source; later sources receive explicitly owned rows only. Named-source legacy handling, existing labels and sidecar ownership remain unchanged.
- [ ] #4 Ctrl-C prevents later sources from starting. Gmail graceful pause commits completed work and restores its signal handler; sync-check propagates interruption and closes an interrupted listing provider.
- [ ] #5 Synthetic regressions fail on the original behavior, focused checks and independent review pass, and the unchanged full mandatory-browser gate passes before local integration.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 95251cc64f328890362757de49d194fa8ca256fe. 1. Claim and commit this plan before source edits. Own only cmd_update_labels/cmd_sync_check and their immediate per-source helpers in commands.py, plus relevant maintenance-command tests and this ledger. 2. Add synthetic multi-source regressions for both provider orders, named-source controls, accountless-row preservation, unsupported/empty first sources and interruption; confirm meaningful baseline failures. 3. Iterate the selected source list, extracting existing per-source bodies only as needed to keep early returns local. Include accountless rows only at index zero of the selected list, preserving named-source behavior. Return the existing Gmail paused/completed result to stop the outer sweep without changing standalone pause/CLI semantics. Retain provider and label policies; close the sync listing provider in finally so interruption propagates cleanly. 4. Run focused command/CLI checks, inspect the complete fixed-base diff and obtain independent focused review through the coordinator. Commit with normal hooks. 5. Run the unchanged required full gate with a coordinated private Chromium lease, close only verified criteria, then integrate to clean local master normally. Preserve every existing ref and evidence; no remote or real-mail operations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: still present (commands.py falls back to sources[0] while cli.py help says 'default: all sources'). cmd_sync_check has the same fallback and the same help text; fix both together.

Code recheck confirms both commands fall back to sources[0]. Only update-labels includes accountless rows; sync-check already queries owned rows via get_downloaded_ids(account). The coordinator explicitly resolved the prior TASK-37 proposal hold: bare sweeps preserve accountless eligibility solely for the original first source, later sources process owned rows, and named-source behavior stays unchanged. This is a bounded ordinary bug fix, not authorization to access actual mail, credentials or account status. TASK-98 downloader behavior, schema, TASK-95 cache-integrity work and TASK-111 output semantics remain outside scope. Source ownership is exclusive; no other Ownmail implementation currently overlaps these functions/tests.
<!-- SECTION:NOTES:END -->
