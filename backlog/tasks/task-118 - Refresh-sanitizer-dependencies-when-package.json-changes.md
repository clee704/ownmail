---
id: TASK-118
title: Refresh sanitizer dependencies when package.json changes
status: To Do
assignee: []
created_date: '2026-09-29 06:39'
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
