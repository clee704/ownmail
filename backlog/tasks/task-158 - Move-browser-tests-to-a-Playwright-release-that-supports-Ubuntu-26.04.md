---
id: TASK-158
title: Move browser tests to a Playwright release that supports Ubuntu 26.04
status: To Do
assignee: []
created_date: '2026-11-28 05:40'
labels: []
dependencies: []
priority: low
ordinal: 127000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub's ubuntu-latest image moved to Ubuntu 26.04. The sanitizer's Playwright devDependency is pinned to 1.58.0, which refuses to install Chromium's system dependencies there ("Playwright does not support chromium on ubuntu26.04-x64"), so the 3.12 job stopped before pytest. Pinning the test job to ubuntu-24.04 restores it as a stopgap. Playwright 1.65.1 lists ubuntu26.04 as a supported host. Raise the devDependency to a release that supports it, run the browser suites (Chromium, and WebKit where CONTRIBUTING.md describes it) and the real-renderer PDF tests against its browser, and run the test job on ubuntu-latest. Check whether the AppArmor sysctl step still applies on 26.04.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The sanitizer's Playwright devDependency names a release that installs Chromium on Ubuntu 26.04
- [ ] #2 The required browser tests pass on that release
- [ ] #3 CI's test job runs on ubuntu-latest
<!-- AC:END -->
