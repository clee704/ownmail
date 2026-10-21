---
id: TASK-149
title: Make PDF export usable where Linux blocks the Chromium sandbox
status: Done
assignee:
  - Codex
created_date: '2026-10-19 05:23'
updated_date: '2026-10-21 04:07'
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
- [x] #1 When Chromium cannot start its sandbox, PDF export reports that cause and how to fix it, instead of a stack trace
- [x] #2 README documents the Linux requirement and the fix (for example an AppArmor profile for the Playwright Chromium, or the sysctl), and the chosen approach is recorded in the notes
- [x] #3 The renderer keeps the Chromium sandbox on; any change to that is a maintainer decision recorded in the notes
- [x] #4 A test covers the sandbox-failure message and fails when the detection is removed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 9478a00.
1. Detect Chromium sandbox launch failures before diagnostic truncation and report a concise cause with Linux setup guidance.
2. Document a per-executable AppArmor profile using Chromium upstream guidance. Keep chromiumSandbox enabled; no host policy changes, dependency changes, or unsandboxed fallback.
3. Verify the error through a synthetic renderer failure, demonstrate the regression test fails without detection, review the full diff, and run the required pre-push gate.
4. Commit the implementation and close the task after verified acceptance criteria.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise confirmed: renderer enables the Chromium sandbox, but Python retains only the final 1000 diagnostic characters. No task dependencies. Scope is diagnostics and Linux setup documentation; host configuration and sandbox policy changes are excluded.

Implementation: scan complete renderer diagnostics for Chromium/Playwright sandbox failures before retaining the generic error tail. The error gives non-root/user-namespace guidance and points to the README Linux section. Unknown renderer errors retain their existing diagnostics.
Linux setup: chose an executable-specific AppArmor profile from Chromium upstream guidance (https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md). The README includes executable-path discovery, profile contents, loading, and upgrade handling. No host settings were changed; chromiumSandbox remains true.
Validation: 52 PDF/CLI tests passed with browser tests required, including real Chromium PDF rendering on macOS. All four synthetic sandbox signatures precede a long crash log; all four regression cases failed with detection disabled and passed after restoration. The AppArmor profile was checked against upstream syntax but was not loaded on this macOS host.
Self-review against 9478a00 found no actionable issue; scope remains diagnostics and documentation. Full pre-push gate pending.

Full validation passed: pre-commit run -a --hook-stage pre-push with browser tests required and four xdist workers. Lint, formatting, dependency checks, the complete test suite, and the 95% branch-coverage gate passed.

Implementation committed as 404034d. All acceptance criteria verified. The AppArmor profile remains an administrator-operated setup step; loading it on Linux was outside this macOS validation environment.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PDF export now recognizes sandbox startup failures even when a long crash log follows and reports the cause with setup guidance. README documents a per-executable AppArmor profile. Chromium sandboxing stays enabled. PDF/CLI tests, mutation verification, self-review, and the full pre-push gate passed.
<!-- SECTION:FINAL_SUMMARY:END -->
