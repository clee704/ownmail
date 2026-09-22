---
id: doc-10
title: Developer baseline audit — 2026-09-11
type: other
created_date: '2026-09-11 10:52'
---

Audit baseline: commit `9932143`, with read-only GitHub checks on 2026-09-11.

## Existing baseline

| Area | Evidence |
|---|---|
| Documentation | [README](../../README.md) covers usage, [CONTRIBUTING](../../CONTRIBUTING.md) covers shared developer rules, and [AGENTS](../../AGENTS.md) covers agent rules. Claude and Copilot adapters point to those sources. [doc-3](<doc-3 - AGENTS.md-modernization-—-the-doc-structure-decision.md>) records the split. |
| Backlog.md | [Configuration](../config.yml), tasks, milestones, dependencies, acceptance criteria, implementation notes, and design records are present. [AGENTS](../../AGENTS.md#the-progress-ledger) requires updates during work. |
| Commit conventions | [Conventional Commits and squash policy](../../CONTRIBUTING.md#commit-messages) are documented. Recent commit headers largely follow them. |
| Local checks | Both pre-commit and pre-push hooks were installed at inspection. [Hook configuration](../../.pre-commit-config.yaml) includes file hygiene, Ruff lint/format, deptry, and pytest. |
| Coverage | [pyproject.toml](../../pyproject.toml) enables branch coverage and sets `fail_under = 95`. Validation passed with 2,189 tests, one expected failure, and 95.39% overall coverage including branches. |
| CI configuration | [ci.yml](../../.github/workflows/ci.yml) runs lint, formatting, dependency checks, and tests with coverage across Python 3.10–3.12. Node is installed for sanitizer integration tests. |

## Gaps

1. **Corrected: CI had not reached GitHub.** The remote default branch was still
   `f6c86e561cb671edb1bd824bbaec53f32fd90e57`; the Actions API returned zero
   workflows and runs. The local workflow therefore has no verified remote
   execution. Review the commits intended for publication, obtain separate
   authorization, then verify the published revision's matrix. TASK-42
   published CI on 2026-09-13 and verified the matrix.

2. **Corrected: merge and review rules were not enforced.** GitHub reported `master` as
   unprotected, no rulesets, and merge commits, rebase, and squash all enabled.
   [The landing policy](../../CONTRIBUTING.md#how-changes-land) permits direct
   maintainer commits and requires PRs for risky changes, but does not define
   independent review expectations. No commit-message hook or PR-title check
   enforces the documented Conventional Commit format. Settle proportionate
   review and validation rules while preserving the intended maintainer workflow.
   TASK-42 added the review policy, commit-header checks, two `master`
   rulesets, and squash-only merges, all documented in CONTRIBUTING.

3. **Corrected: historical Done records had unchecked or accidental criteria.** Nine
   tasks are affected: TASK-1.2, TASK-1.5, TASK-2.1 through TASK-2.6, and TASK-15.
   The six TASK-2 subtasks contain sixteen number-only criteria. For example,
   [TASK-2.6](<../tasks/task-2.6 - Add-pre-commit-hooks-GitHub-Actions-CI-for-ruff-pytest.md>)
   is Done with ten unchecked criteria, five containing only numbers. Audit
   implementation and decision evidence before correcting status or checkboxes;
   distinguish superseded requirements from completed implementation.
   TASK-42 removed the number-only criteria, checked criteria met by the
   repository, and prefixed each unmet criterion with the decision that
   superseded it. No task was reopened.

4. **Corrected: the pre-push test hook skipped non-Python changes.** At the audit baseline,
   its `types: [python]` filter and missing `always_run` caused
   `pre-commit run pytest --hook-stage pre-push --files pyproject.toml .github/workflows/ci.yml`
   to report `Skipped (no files to check)`. Dependency, CI, or sanitizer changes
   could therefore miss the local test gate. TASK-43 adds `always_run: true`
   to make the full suite run for every pre-push invocation. Repeating the
   check with only configuration and sanitizer JavaScript paths ran the full
   suite successfully.

5. **Corrected: contributor documentation had stale values.** At the audit baseline,
   CONTRIBUTING listed 80% coverage instead of the configured 95%, and its setup
   comment said tests run on commit despite the documented push-stage split.
   TASK-43 corrects both and clarifies that schemas already used by existing
   archives require migrations even before v1.0.0.

## Evidence and follow-up

Remote state was checked with `gh api` against
`repos/clee704/ownmail/actions/workflows`, `actions/runs`, `branches/master`,
`branches/master/protection`, `rulesets`, and the repository settings endpoint.
These are a dated snapshot; repeat them before changing remote configuration.

[TASK-42](<../tasks/task-42 - Close-repository-review-CI-and-backlog-governance-gaps.md>)
consolidates publication, branch and merge enforcement, review and commit
validation, and historical ledger repair. Hook and contributor-document fixes
are tracked in [TASK-43](<../tasks/task-43 - Align-quality-gates-and-documentation-with-repository-policy.md>).
This audit changed no remote settings or historical
acceptance criteria.
