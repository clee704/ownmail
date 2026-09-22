---
id: TASK-110
title: Retry throttled Gmail live batches without losing successful members
status: To Do
assignee: []
created_date: '2026-09-22 05:48'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live refreshes can receive per-message HTTP 429 responses inside a successful Gmail batch. The live path has no bounded member retry, leaving the source incomplete until a later run. Reuse provider request limits and add bounded backoff for transient failures while preserving successful members and conservative handling of permanent errors.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Transient member failures are retried within a bounded budget without repeating successful reads.
- [ ] #2 Exhausted and permanent failures preserve retryable state and report an incomplete refresh.
<!-- AC:END -->
