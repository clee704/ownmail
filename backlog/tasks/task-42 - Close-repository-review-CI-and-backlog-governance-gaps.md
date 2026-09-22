---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: In Progress
assignee: []
created_date: '2026-09-11 10:52'
updated_date: '2026-09-22 17:25'
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
- [x] #1 Review the commits intended for publication; after separate authorization, publish the reviewed CI changes and record passing lint and Python-matrix runs at the published revision.
- [ ] #2 Decide and document branch protection and merge-method enforcement consistent with the maintainer workflow; apply authorized remote settings and verify them.
- [ ] #3 Document proportionate independent review expectations and implement Conventional Commit validation for direct commits and PR titles without adding runtime dependencies.
- [x] #4 Repair the nine historical Done tasks identified in doc-10 using implementation and decision evidence; remove number-only accidental criteria and reopen or explicitly supersede any unmet requirement.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Publication and a rewrite of unpublished history were authorized on 2026-09-13. AC 1 is complete; the remaining governance criteria are outside this pass.

Removed personal export paths, archive statistics, and a real folder hierarchy from unpublished historical task and design notes. The TASK-27 message-ID examples are synthetic placeholders; its install-specific counts were generalized. Prepared the rewrite in a separate local copy and verified all 164 rewritten commits retain their parent relationships and author/committer metadata. Changes were confined to the intended documentation, the final file tree matched the sanitized original, and published commit f6c86e5 remained unchanged. Updated .git-blame-ignore-revs for the rewritten formatting commit.

Independent verification found none of the identified private-data markers in outgoing blobs or commit bodies. Additional private-path, phone, and IP scans found no further issue. Gitleaks 8.30.1 found no credentials. Pushed only master, without force or backup refs.

The first CI run exposed a formatter-version mismatch. Pinning development Ruff to 0.15.0 aligned CI with the existing pre-commit hook. No runtime dependency or test gate changed.

Published revision 0871bc681333eef3feae63984e52d53c97a7d2c1 passed lint, formatting, deptry, and the Python 3.10/3.11/3.12 matrix in [CI run 34774617015](https://github.com/clee704/ownmail/actions/runs/34774617015). Each Python job passed 2,384 tests with one expected failure, zero skips, and 95.52% coverage including branches. The local full pre-push gate passed with 95.55% coverage. Both exceed the 95% minimum.

Historical ledger repair (AC 4): removed the sixteen number-only criteria from TASK-2.1 through TASK-2.6 and checked the criteria met by the current repository. Each unmet criterion now begins with the decision that superseded it: the mbsync and notmuch NO-GOs for TASK-1.2 and TASK-1.5, the Python 3.10 floor for TASK-2.6 #3, and the rejected Trash-archiving branch for TASK-15 #2. TASK-15 #3 is met by docs/philosophy.md and config.example.yaml. No requirement needed reopening.
<!-- SECTION:NOTES:END -->
