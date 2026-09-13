---
id: TASK-56
title: Preserve qualified body selectors when rendering HTML messages
status: To Do
assignee: []
created_date: '2026-09-13 06:30'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CSS sanitizer scopes a selector such as body[class=main] .logo under the reader container, but body extraction removes the matching body element and its attributes. Preserve the authored selector relationship without allowing styles to affect the app shell.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A synthetic message with a qualified body selector retains the intended descendant styling after sanitization and body extraction.
- [ ] #2 The preserved styles remain scoped to message content.
<!-- AC:END -->
