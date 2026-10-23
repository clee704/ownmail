---
id: TASK-153
title: Update encoding audit queries for the current email identifier
status: To Do
assignee: []
created_date: '2026-10-23 06:53'
labels: []
dependencies: []
priority: low
type: bug
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/audit_encoding.py selects message_id from emails, but the current archive schema uses email_id. The audit fails before scanning a current archive. Update its query and row naming, with a synthetic current-schema regression.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The encoding audit scans a synthetic archive using the current email_id schema.
- [ ] #2 The full pre-push gate passes and the fix is committed.
<!-- AC:END -->
