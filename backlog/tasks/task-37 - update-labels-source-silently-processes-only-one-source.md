---
id: TASK-37
title: update-labels --source silently processes only one source
status: To Do
assignee: []
created_date: '2026-08-06 19:22'
labels: []
dependencies: []
ordinal: 41000
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
