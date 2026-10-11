---
id: TASK-143
title: Cut test suite run time
status: In Progress
assignee: []
created_date: '2026-10-11 22:23'
updated_date: '2026-10-11 22:24'
labels:
  - testing
dependencies: []
priority: medium
type: chore
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The pre-push gate takes about five minutes. A profile showed about 370 tests (7% of the suite) taking 87% of the time: browser tests start Node and launch a new Chromium per test, retry tests sleep through real Retry-After delays, the stuck-renderer PDF test waits out its real grace period, and the suite runs in a single process. Coverage adds about 9%. CONTRIBUTING.md and .pre-commit-config.yaml still quote ~11s. Reduce wall time without weakening any test: every changed test must still fail when the behavior it covers is broken.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Retry and cleanup tests no longer wait in real time; each still asserts the delay or bound it covers and fails when the retry or kill path is broken
- [ ] #2 Browser tests reuse one browser per test process, each test still gets a fresh browser context, and the tests still fail when the behavior they cover is broken
- [ ] #3 The pre-push hook and CI run the suite in parallel with pytest-xdist, the coverage gate still applies, and repeated full runs show no new flaky failures
- [ ] #4 CONTRIBUTING.md and .pre-commit-config.yaml state the measured run time
- [ ] #5 The full pre-push gate passes with browser tests required
<!-- AC:END -->
