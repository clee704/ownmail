---
id: TASK-129
title: PDF export for archived messages
status: To Do
assignee: []
created_date: '2026-09-30 16:53'
labels: []
milestone: m-4
dependencies:
  - TASK-9
references:
  - backlog/tasks/task-9 - Email-export-ownmail-export-format-mbox-pdf.md
priority: medium
type: feature
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split from TASK-9 under its explicit PDF alternative. Add PDF export for archived messages selected with the existing query syntax when a concrete document-export need justifies the rendering cost. Keep mbox export independent. Select and document the rendering approach and output layout; follow the repository approval rule before adding any runtime dependency. Active-only cache export and label-header synthesis are outside this follow-up.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ownmail export --format pdf supports archived messages filtered with the existing --query syntax
- [ ] #2 The selected PDF renderer and output behavior are documented, with any required runtime dependency approved before introduction
- [ ] #3 Synthetic fixtures verify readable plain-text and HTML message output, headers, and clear attachment treatment without modifying source mail
<!-- AC:END -->
