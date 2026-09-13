---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: In Progress
assignee: []
created_date: '2026-09-11 10:52'
updated_date: '2026-09-13 18:18'
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
Publication and a rewrite of unpublished history were authorized on 2026-09-13. This pass covers AC 1; the remaining governance criteria are outside the requested scope.

Local validation passed Ruff lint/format, deptry, file hygiene, and 2,384 tests with one expected failure and no skips. Overall coverage including branches was 95.55%, above the 95% minimum. Gitleaks 8.30.1 and complementary review found no credentials in the tracked files or scanned history.

Privacy review confirmed personal export paths and archive statistics in historical TASK-1.1, TASK-1.3, and TASK-7. Current files are sanitized; the rewrite will remove those details from unpublished versions and generalize install-specific wording in TASK-1.2 and TASK-27. A deeper check corrected the initial classification of TASK-27 message-ID examples: they are synthetic placeholders. Its observed counts still need generalization.

Prepare the rewrite in a separate local copy, preserve published commits and the application tree, rescan the exact publication history, then push master and verify remote lint and Python 3.10-3.12 runs, including skip counts. GitHub Actions is enabled, but the workflow has not yet been published.

The final privacy pass also generalized a real folder hierarchy in TASK-26 and a deleted historical design document, preserving the reproduction with a synthetic child label.
<!-- SECTION:NOTES:END -->
