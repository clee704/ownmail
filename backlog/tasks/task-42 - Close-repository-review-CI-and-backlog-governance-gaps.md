---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: In Progress
assignee: []
created_date: '2026-09-11 10:52'
updated_date: '2026-09-13 09:44'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Publication validation started: review outgoing history for personal data and credentials, run the full local quality gate, then publish only after the review clears and verify CI at the published revision. This pass covers AC 1; the remaining governance criteria are outside the requested scope.

Local Ruff lint/format, deptry, file hygiene, and the full pre-push test gate passed. Overall statement and branch coverage is 95.55%, above the 95% minimum. Gitleaks 8.30.1 reported no credential findings across reachable history and the tracked-file snapshot; complementary review found only mocked credentials and existing public maintainer attribution. Privacy review found install-specific archive statistics in TASK-1.1 and TASK-1.3; current notes are sanitized. Historical versions also contain private message identifiers in TASK-27 that were removed from the current tree. Publication remains blocked because those versions would be sent by a normal push. Rewriting unpublished history requires explicit authorization under AGENTS.md. GitHub Actions is enabled but origin/master has no workflow or runs, so remote lint and Python-matrix execution remains unverified. After authorized sanitization, rescan the exact publication history, push only the intended branch without force or backup refs, and inspect CI results and skip counts. Other TASK-42 criteria remain outside this pass.

The final local run passed 2,384 tests with one expected failure and no skips. Further privacy review sanitized the current TASK-7 export path and count and generalized an install-specific account-count rationale in TASK-1.2. Confirmed historical findings span TASK-1.1, TASK-1.3, TASK-7, and TASK-27, beginning at cf9b4fa; preserve origin/master history and scrub only unpublished descendants after approval. This targeted review cannot guarantee absence of every possible personal-data pattern.
<!-- SECTION:NOTES:END -->
