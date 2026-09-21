---
id: TASK-105
title: Hide Active details and report message freshness accurately
status: In Progress
assignee: []
created_date: '2026-09-21 07:28'
labels: []
dependencies: []
priority: high
ordinal: 106000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Remove Active/check-time text from message list rows. Hide reader Active details until a kebab-menu action opens them. Diagnose widespread incomplete warnings and show specific per-message freshness instead of treating unrelated source failures as unconfirmed message state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Message list rows contain no Active freshness line and retain valid attachment accessibility references.
- [ ] #2 Reader Active details appear only after selecting a kebab-menu item, with accessible close behavior.
- [ ] #3 Freshness distinguishes current confirmed messages, unknown lifecycle state, stale observations and account-level refresh problems; live warning causes are investigated and addressed where in scope.
- [ ] #4 Relevant UI and state tests, required checks, review and clean committed delivery are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base f471ad7. Use existing menu/panel patterns. Diagnose live status with aggregate metadata and read-only provider observations. Work in an isolated checkout before applying to the running server.
<!-- SECTION:PLAN:END -->
