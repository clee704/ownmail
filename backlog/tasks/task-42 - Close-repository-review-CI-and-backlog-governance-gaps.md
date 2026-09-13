---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: In Progress
assignee: []
created_date: '2026-09-11 10:52'
updated_date: '2026-09-13 18:24'
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

Removed personal export paths, archive statistics, and a real folder hierarchy from unpublished historical task and design notes. Corrected the initial classification of TASK-27 message-ID examples: they are synthetic placeholders; only its install-specific counts needed generalization.

Prepared the rewrite in a separate local copy. Verified all 164 outgoing commits retain their parent relationships and author/committer metadata; changes are confined to the intended documentation. The rewritten tip has the same file tree as the sanitized original, and published commit f6c86e5 remains unchanged. Independent verification found none of the identified private-data markers in the outgoing blobs or commit bodies. Gitleaks 8.30.1 found no credentials. Updated the formatting revision in .git-blame-ignore-revs for the rewritten history.

Local validation passed Ruff lint/format, deptry, file hygiene, and 2,384 tests with one expected failure and no skips; overall coverage including branches was 95.55%, above the 95% minimum. Publish master and verify the remote lint and Python 3.10-3.12 jobs, including skip counts, before checking AC 1.

The first published CI run (34774436331) exposed a formatter mismatch: the pre-commit hook pins Ruff 0.15.0, but the development dependency allowed CI to install Ruff 0.16.7, which also checks Markdown code blocks. Pin the development dependency to 0.15.0 so local hooks and CI enforce the same formatter version.
<!-- SECTION:NOTES:END -->
