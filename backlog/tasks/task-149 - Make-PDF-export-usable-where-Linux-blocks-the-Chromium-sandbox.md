---
id: TASK-149
title: Make PDF export usable where Linux blocks the Chromium sandbox
status: To Do
assignee: []
created_date: '2026-10-19 05:23'
updated_date: '2026-10-19 05:23'
labels:
  - bug
dependencies: []
priority: medium
ordinal: 24500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pdf_renderer.js launches Chromium with chromiumSandbox: true. Ubuntu 23.10 and later restrict unprivileged user namespaces through AppArmor by default, so Chromium cannot start its sandbox and aborts. On ubuntu-24.04 CI the real-renderer tests in tests/test_pdf_export.py aborted with SIGABRT and passed once CI lifted the restriction with sysctl (117b826), which confirms the cause and hides the failure from the suite. A user on such a system gets 'PDF renderer unavailable or failed' followed by the last 1000 characters of Chromium's stderr, which is a register dump and omits Chromium's own error line. Running without the sandbox is not an option to take silently, because the renderer loads untrusted message HTML.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When Chromium cannot start its sandbox, PDF export reports that cause and how to fix it, instead of a stack trace
- [ ] #2 README documents the Linux requirement and the fix (for example an AppArmor profile for the Playwright Chromium, or the sysctl), and the chosen approach is recorded in the notes
- [ ] #3 The renderer keeps the Chromium sandbox on; any change to that is a maintainer decision recorded in the notes
- [ ] #4 A test covers the sandbox-failure message and fails when the detection is removed
<!-- AC:END -->
