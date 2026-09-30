---
id: TASK-118
title: Refresh sanitizer dependencies when package.json changes
status: In Progress
assignee: []
created_date: '2026-09-29 06:39'
updated_date: '2026-09-30 01:36'
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
- [ ] #1 When installed dependencies no longer satisfy package.json, the next ownmail serve installs satisfying versions before starting the sanitizer, and an install that already satisfies it starts without running npm
- [ ] #2 When the refresh cannot run (npm missing, offline or a failed install), the outcome is defined, reported to the user and covered by tests
- [ ] #3 Startup guidance for a failed sanitizer install works for pipx and source installs, and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 654e88c.
1. Decide staleness without running npm: compare each package.json dependency with the version in node_modules/<name>/package.json using a caret-range check. No stamp file, so an install that already meets package.json never runs npm.
2. When a dependency is missing or outside its range, run npm install with --omit=dev (replacing the deprecated --production), keeping dev dependencies on a tree that already has them. Stop npm with SIGTERM on timeout so it can roll back, and check the versions again afterwards.
3. A refresh that cannot run leaves the sanitizer stopped, and serve keeps refusing to serve without it. The sanitizer records why and what to do, and serve prints that in place of the source-checkout-only command, naming the install directory so the guidance works for pipx and source installs.
4. Tests over a temporary sanitizer directory with a fake npm; a guard that the shipped package.json uses only ranges the check understands; README and setup docs for the network requirement after an update; the full pre-push gate.
<!-- SECTION:PLAN:END -->
