---
id: TASK-67
title: Review sanitizer dependency audit findings
status: To Do
assignee: []
created_date: '2026-09-13 19:07'
labels: []
dependencies: []
priority: high
type: chore
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A development install reported npm audit findings in the existing sanitizer dependency tree: DOMPurify, PostCSS, nanoid and ws. Verify the advisories against installed and supported versions, assess exposure in the sanitizer worker, and apply bounded dependency updates with regression coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Advisories and sanitizer exposure are documented against the dependency versions in use.
- [ ] #2 Applicable dependency fixes are validated by sanitizer regressions and the full pre-push gate, with any remaining findings explained.
<!-- AC:END -->
