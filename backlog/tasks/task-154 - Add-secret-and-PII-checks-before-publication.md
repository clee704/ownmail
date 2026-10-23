---
id: TASK-154
title: Add secret and PII checks before publication
status: To Do
assignee: []
created_date: '2026-10-23 07:11'
labels:
  - security
dependencies: []
priority: medium
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub secret scanning and push protection are enabled, but local hooks and CI have no credential or general PII scanner. Add repository checks that catch secrets and operator-specific personal data before publication. Keep documented synthetic fixtures and public project attribution usable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Local hooks and CI scan outgoing content for supported credential patterns and targeted PII patterns, including personal home paths and account details.
- [ ] #2 Scanner diagnostics identify locations with sensitive values redacted; any allowlist is narrow, documented, and preserves detection outside its intended fixture.
- [ ] #3 Synthetic positive and negative cases prove the checks reject prohibited content and accept reserved example data and intended public project attribution.
- [ ] #4 Document the checks, their limits, prerequisites, and commands for scanning tracked content and an outgoing commit range without reading ignored archives or configuration.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Audit at 10c2f60: Gitleaks 8.30.1 reported no secrets in the tracked HEAD snapshot or master history (818 commits scanned). GitHub reported no open or resolved secret-scanning alerts. A separate targeted scan of tracked text, decoded email fixtures, recent patches, and commit messages found no unexpected personal paths, phone or SSN patterns, or private tunnel hosts. Reviewed address candidates were examples or synthetic test data. Public author attribution and Git identity metadata remain visible. These checks establish no comprehensive guarantee for free-form personal data. Local hooks currently cover hygiene, Ruff, dependency usage, tests and commit headers; CI covers lint, tests and commit headers. GitHub non-provider secret patterns are disabled. No history rewrite or remote security-setting change was made.
<!-- SECTION:NOTES:END -->
