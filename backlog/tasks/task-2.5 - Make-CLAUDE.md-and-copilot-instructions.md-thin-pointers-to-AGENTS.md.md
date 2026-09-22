---
id: TASK-2.5
title: Make CLAUDE.md and copilot-instructions.md thin pointers to AGENTS.md
status: Done
assignee: []
created_date: '2026-07-24 04:43'
updated_date: '2026-09-22 17:25'
labels: []
milestone: m-2
dependencies:
  - TASK-2.1
parent_task_id: TASK-2
priority: low
ordinal: 8
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Once AGENTS.md exists (TASK-2.1), add a CLAUDE.md at repo root that imports it (a CLAUDE.md containing just '@AGENTS.md' plus a one-line note on why), and rewrite .github/copilot-instructions.md to point at AGENTS.md instead of duplicating its content, so every AI tool (Claude Code, Copilot, Codex, etc.) reads the same operating contract from one source.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CLAUDE.md exists and imports AGENTS.md
- [x] #2 .github/copilot-instructions.md no longer duplicates AGENTS.md content
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Ledger repair, 2026-09-22 (TASK-42).** Removed number-only accidental criteria and checked the remaining criteria against the current repository.
<!-- SECTION:NOTES:END -->
