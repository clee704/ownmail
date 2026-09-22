---
id: TASK-2.3
title: Retire ROADMAP.md — convert its content into backlog tasks
status: Done
assignee: []
created_date: '2026-07-24 04:42'
updated_date: '2026-09-22 17:25'
labels: []
milestone: m-2
dependencies: []
parent_task_id: TASK-2
priority: medium
ordinal: 9
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Convert ROADMAP.md's three sections into proper backlog tasks/docs via the backlog CLI: 'Next Up — Import & Scan' (import/scan commands, provider-id strategy, code-change notes) and 'Next Up — Web UI Polish' each become an umbrella task with subtasks as needed; 'Backlog' items (Email Export, Headless Server Support, Encryption at Rest) become standalone low/medium-priority tasks. Delete ROADMAP.md once its content lives in backlog/, and drop the dangling CONTRIBUTING.md/README.md references to it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All ROADMAP.md content has a corresponding backlog task or doc
- [x] #2 ROADMAP.md deleted, no remaining references to it in the repo
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Ledger repair, 2026-09-22 (TASK-42).** Removed number-only accidental criteria and checked the remaining criteria against the current repository.
<!-- SECTION:NOTES:END -->
