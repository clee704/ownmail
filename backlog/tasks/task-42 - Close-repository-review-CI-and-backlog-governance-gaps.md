---
id: TASK-42
title: 'Close repository review, CI, and backlog governance gaps'
status: Done
assignee: []
created_date: '2026-09-11 10:52'
updated_date: '2026-09-22 17:41'
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
- [x] #2 Decide and document branch protection and merge-method enforcement consistent with the maintainer workflow; apply authorized remote settings and verify them.
- [x] #3 Document proportionate independent review expectations and implement Conventional Commit validation for direct commits and PR titles without adding runtime dependencies.
- [x] #4 Repair the nine historical Done tasks identified in doc-10 using implementation and decision evidence; remove number-only accidental criteria and reopen or explicitly supersede any unmet requirement.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Publication and a rewrite of unpublished history were authorized on 2026-09-13. That pass completed AC 1; the other criteria were completed on 2026-09-22.

Removed personal export paths, archive statistics, and a real folder hierarchy from unpublished historical task and design notes. The TASK-27 message-ID examples are synthetic placeholders; its install-specific counts were generalized. Prepared the rewrite in a separate local copy and verified all 164 rewritten commits retain their parent relationships and author/committer metadata. Changes were confined to the intended documentation, the final file tree matched the sanitized original, and published commit f6c86e5 remained unchanged. Updated .git-blame-ignore-revs for the rewritten formatting commit.

Independent verification found none of the identified private-data markers in outgoing blobs or commit bodies. Additional private-path, phone, and IP scans found no further issue. Gitleaks 8.30.1 found no credentials. Pushed only master, without force or backup refs.

The first CI run exposed a formatter-version mismatch. Pinning development Ruff to 0.15.0 aligned CI with the existing pre-commit hook. No runtime dependency or test gate changed.

Published revision 0871bc681333eef3feae63984e52d53c97a7d2c1 passed lint, formatting, deptry, and the Python 3.10/3.11/3.12 matrix in [CI run 34774617015](https://github.com/clee704/ownmail/actions/runs/34774617015). Each Python job passed 2,384 tests with one expected failure, zero skips, and 95.52% coverage including branches. The local full pre-push gate passed with 95.55% coverage. Both exceed the 95% minimum.

Historical ledger repair (AC 4): removed the sixteen number-only criteria from TASK-2.1 through TASK-2.6 and checked the criteria met by the current repository. Each unmet criterion now begins with the decision that superseded it: the mbsync and notmuch NO-GOs for TASK-1.2 and TASK-1.5, the Python 3.10 floor for TASK-2.6 #3, and the rejected Trash-archiving branch for TASK-15 #2. TASK-15 #3 is met by docs/philosophy.md and config.example.yaml. No requirement needed reopening.

Review and commit validation (AC 3): CONTRIBUTING now defines review by change type. Direct commits need self-review, PR-route changes need a reviewer who did not write them, and outside PRs need maintainer review. scripts/check_commit_msg.py is a stdlib check of the documented types and the 72-character limit. It runs as a pre-commit commit-msg hook and in .github/workflows/commits.yml for pushed ranges and PR titles; the workflow re-runs on title edits. Tests cover each input mode and fail against broken length, first-line, and new-branch handling. The Commits workflow checked the published push range in [run 35761264171](https://github.com/clee704/ownmail/actions/runs/35761264171). The PR-title path is covered by unit tests; no PR has exercised it on GitHub yet.

Branch and merge enforcement (AC 2), authorized 2026-09-22: ruleset "master integrity" blocks deletion and force pushes with no bypass. Ruleset "master merge gate" requires a PR, squash merges, and the lint, test (3.10/3.11/3.12), and conventional checks, with repository admins bypassing so maintainers can still commit directly. Repository settings allow only squash merges, titled and described from the PR. Read back through the branch rules API. A direct push to master after the rulesets took effect succeeded through the admin bypass. Required approvals are zero because a sole maintainer cannot approve their own PR; review stays a documented policy. CONTRIBUTING and doc-10 record the decision.
<!-- SECTION:NOTES:END -->
