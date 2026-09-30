---
id: TASK-118
title: Refresh sanitizer dependencies when package.json changes
status: Done
assignee:
  - Ownmail IC1
created_date: '2026-09-29 06:39'
updated_date: '2026-09-30 04:56'
labels:
  - web
dependencies: []
priority: medium
type: bug
ordinal: 9750
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
HtmlSanitizer._ensure_deps runs npm install only when ownmail/sanitizer/node_modules is missing. An install that keeps that directory, such as a source checkout or an in-place package upgrade, keeps the versions resolved at its first launch even after package.json raises a floor. TASK-67 raised the DOMPurify and PostCSS floors because of published advisories, and those installs keep the flagged versions until node_modules is removed. TASK-67 found none of those advisories reachable once the worker ignores source-map comments, but a later fix may be. pipx reinstall recreates the environment and resolves current versions. package-lock.json is not tracked, so nothing records which versions an install should have.

The same path has two smaller problems. When the sanitizer fails to start, ownmail serve tells the user to run cd ownmail/sanitizer && npm install, which works only from a source checkout. The install passes npm's --production flag, which npm 11 reports as deprecated in favor of --omit=dev.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When installed dependencies no longer satisfy package.json, the next ownmail serve installs satisfying versions before starting the sanitizer, and an install that already satisfies it starts without running npm
- [x] #2 When the refresh cannot run (npm missing, offline or a failed install), the outcome is defined, reported to the user and covered by tests
- [x] #3 Startup guidance for a failed sanitizer install works for pipx and source installs, and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Verify direct installed package metadata against the full current stable caret ranges using stdlib, including upper bounds and prerelease exclusion. Satisfying installs bypass npm entirely. Missing or stale packages refresh with --omit=dev; verify the resulting versions before worker startup. Missing npm, offline failure, timeout or unsuccessful refresh leave sanitizer unavailable and serving refused. Limit edits to sanitizer setup, owned run_server guidance/tests and this ledger; manager integrates README proposal. Run focused tests and mutation checks, then coordinated required browser/full coverage/pre-push gates and full-base author review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC1. Branch: fix/sanitizer-dependency-refresh. Review base: common claim base c44eb0f620d79e9be10ff8449969408adac6341b. Implementation checkpoint: 69f35e0.

Scope remained in sanitizer dependency setup, run_server startup guidance, sanitizer tests and TestRunServer. Dependency declarations, charset decoding, shared README and integration checkout were untouched. Manager owns serialized integration and the separate README wording proposal.

Premise verified: existing node_modules bypassed current dependency declarations. Installed direct package metadata now must satisfy each full current stable nonzero-major caret range, including the incompatible upper bound and prerelease exclusion. Unknown range syntax or malformed/missing/unreadable metadata fails closed; future declaration syntax outside this grammar needs an explicit checker extension. Satisfying installations need neither npm lookup nor invocation. Missing/stale dependencies refresh with --omit=dev and are checked again before launching the worker. No runtime dependency was added and the sanitizer security boundary is unchanged.

Missing npm, offline/install failure, timeout, filesystem errors and ineffective successful installs leave the worker unavailable and serving refused. Startup prints retry and repair guidance usable from pipx and source installs.

Planning chronology: the supported backlog --plan checkpoint was written before substantive edits. Its initial commit attempt preceded implementation but failed because isolated development tooling was not yet installed. The successful plan checkpoint commit (42a8983) followed implementation edits; that chronology is intentional and is not represented as a prior commit.

Validation: 129 focused sanitizer/startup tests passed including actual Node integration. Four deliberate mutations were detected: directory-only trust, missing upper bound, prerelease acceptance and skipped post-install verification. Source was restored. Disposable real-npm probes verified stale node_modules plus old lockfile refresh, the no-npm satisfied path and safe ENOTCACHED offline failure. Required Chromium browser full suite passed: 3939 passed, 1 expected xfailed, zero skipped; branch-inclusive coverage 96.44%. Ruff check, format-check and deptry passed. Exact pre-commit run -a --hook-stage pre-push passed, including required browser coverage. Narrow headless execution escalation resolved the macOS sandbox bootstrap restriction; no product assertions or system settings changed.

Author self-reviewed the entire task diff against the common claim base and found no outstanding issue. Per the current ordinary-fix review contract, an additional independent reviewer was not required. All acceptance criteria are verified. Final ledger closure commit follows the coordinated short measurement hold; manager then integrates TASK-118 before TASK-40 and applies the separately proposed README wording.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Sanitizer startup now refreshes missing or incompatible dependencies, preserves the offline no-npm fast path for satisfying installs, verifies installation results and reports usable pipx/source repair guidance. Full required browser/coverage/pre-push gates and meaningful regression mutation checks passed; no blockers remain.
<!-- SECTION:FINAL_SUMMARY:END -->
