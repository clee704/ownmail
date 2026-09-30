---
id: TASK-118
title: Refresh sanitizer dependencies when package.json changes
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-29 06:39'
updated_date: '2026-09-30 04:52'
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
- [ ] #3 Startup guidance for a failed sanitizer install works for pipx and source installs, and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Verify direct installed package metadata against the full current stable caret ranges using stdlib, including upper bounds and prerelease exclusion. Satisfying installs bypass npm entirely. Missing or stale packages refresh with --omit=dev; verify the resulting versions before worker startup. Missing npm, offline failure, timeout or unsuccessful refresh leave sanitizer unavailable and serving refused. Limit edits to sanitizer setup, owned run_server guidance/tests and this ledger; manager integrates README proposal. Run focused tests and mutation checks, then coordinated required browser/full coverage/pre-push gates and full-base author review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC1. Reserved for TASK-118. Review base: 654e88c2836e1426732b46b87ec8fa5ea3ced40c. Branch: fix/sanitizer-dependency-refresh.
Intended scope: ownmail/sanitizer/__init__.py, especially HtmlSanitizer._ensure_deps and startup failure reporting; ownmail/web.py run_server sanitizer-startup guidance only; tests/test_sanitizer.py dependency/startup cases and tests/test_web.py TestRunServer; this task file. Existing dependency declarations are inputs; no new runtime dependency or changed sanitizer security boundary is included.
Ownmail IC2 owns body charset recovery in ownmail/parser.py and the web decoding functions and their tests. Both tasks touch ownmail/web.py and tests/test_web.py in separate function/test families. Preserve the other task's scope and fixtures. Implementation uses separate worktrees; integration is serialized in TASK-118 then TASK-40 order. Shared imports or helpers, overlapping test changes and unresolved security behavior must be reported before expanding scope. The integration checkout, README files and execution-order document are reserved for the manager. No real archive or server operation is included.
Next action: Ownmail IC1 creates its isolated worktree from the common claim base, verifies the current dependency-refresh premise and existing alternatives, and records its bounded implementation plan before substantive work.

Premise verified: existing node_modules currently bypasses all dependency checks. Runtime declarations remain unchanged. Review base for this isolated implementation is common claim base c44eb0f620d79e9be10ff8449969408adac6341b.

Implementation validates each current stable nonzero-major caret requirement against direct installed metadata, including upper bounds and prerelease exclusion. Unsupported requirement syntax fails closed with a diagnostic. Satisfying metadata bypasses npm lookup and invocation; refresh uses --omit=dev and revalidates before worker startup. Missing npm, offline/install errors, timeout, filesystem errors and an ineffective successful install all leave the worker unavailable. Consolidated duplicate dependency tests into isolated fixtures; 129 sanitizer/startup tests passed including actual Node integration. Regression tests detected four deliberate mutations (old directory shortcut, omitted upper bound, accepted prereleases and skipped post-install verification), after which source was restored. Ruff check, format-check and deptry pass. Plan was recorded through backlog before substantive edits; its initial commit attempt was blocked by missing isolated dev tooling, and successful plan commit followed implementation edits. Required full browser/coverage/pre-push validation remains pending.

Required Chromium browser coverage passed with synthetic fixtures: 3939 passed, 1 expected xfailed, no skipped tests; branch-inclusive coverage 96.44%. A narrow headless-test escalation was needed after macOS sandbox browser bootstrap/kill restrictions; no product assertions or security settings changed. A disposable real-npm probe confirmed that a retained node_modules directory and old lockfile refresh after the manifest floor changes, a satisfying install runs without npm, and an offline stale refresh reports ENOTCACHED and fails safely. Author reviewed the full task diff from common claim base: edits remain in owned sanitizer/startup scopes, no runtime dependencies or security boundary changed. Exact final pre-push gate remains pending.
<!-- SECTION:NOTES:END -->
