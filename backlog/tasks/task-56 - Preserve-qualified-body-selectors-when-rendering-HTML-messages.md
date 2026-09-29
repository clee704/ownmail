---
id: TASK-56
title: Preserve qualified body selectors when rendering HTML messages
status: To Do
assignee: []
created_date: '2026-09-13 06:30'
updated_date: '2026-09-29 05:40'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CSS sanitizer scopes a selector such as body[class=main] .logo under the reader container, but body extraction removes the matching body element. Since TASK-94, _extract_body_content copies the body's style onto #ownmail-email-content; its class, id, bgcolor, and other attributes are still dropped, so body.main and body[class=main] selectors never match. Preserve the authored selector relationship without allowing styles to affect the app shell.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A synthetic message with a qualified body selector retains the intended descendant styling after sanitization and body extraction.
- [ ] #2 The preserved styles remain scoped to message content.
<!-- AC:END -->
