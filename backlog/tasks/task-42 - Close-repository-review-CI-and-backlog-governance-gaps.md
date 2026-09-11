---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: To Do
assignee: []
created_date: '2026-09-11 10:52'
labels: []
dependencies: []
documentation:
  - backlog/docs/doc-10 - Developer-baseline-audit-—-2026-09-11.md
priority: medium
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Complete the governance follow-ups from doc-10. Local lint, coverage, documentation separation, and Backlog.md already exist. The remaining work is to make remote CI and merge policies effective, define proportionate review and commit validation, and reconcile historical Done records with their acceptance criteria. The separately tracked hook and contributor-document corrections are outside this task. Publishing local commits or changing remote settings requires separate authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Review the commits intended for publication; after separate authorization, publish the reviewed CI changes and record passing lint and Python-matrix runs at the published revision.
- [ ] #2 Decide and document branch protection and merge-method enforcement consistent with the maintainer workflow; apply authorized remote settings and verify them.
- [ ] #3 Document proportionate independent review expectations and implement Conventional Commit validation for direct commits and PR titles without adding runtime dependencies.
- [ ] #4 Repair the nine historical Done tasks identified in doc-10 using implementation and decision evidence; remove number-only accidental criteria and reopen or explicitly supersede any unmet requirement.
<!-- AC:END -->
