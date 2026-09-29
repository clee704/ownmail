---
id: TASK-117
title: Block remote fonts and media while images are blocked
status: To Do
assignee: []
created_date: '2026-09-29 05:40'
updated_date: '2026-09-29 05:40'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 9500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Image blocking stops every remote image through the message response's CSP img-src (TASK-72), but other remote content still loads. The sanitizer keeps @font-face sources from any host and remote <video> and <audio> sources. A Chromium check with synthetic messages confirmed that the font and both media files were requested while images were blocked. The worker once allowed @font-face URLs only from trusted font providers; that check was lost when CSS url() was opened up for images, and the comment above scopeAndSanitizeCSS still describes it. Decide which remote fonts and media blocking should cover, including the trusted font providers, and enforce it in the same response policy and reader feedback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With blocking on and an untrusted sender, browser tests confirm the covered fonts and media make no remote requests
- [ ] #2 Loading images or trusting the sender restores the covered content, and the banner and docs describe what blocking covers
- [ ] #3 Sanitizer comments match the enforced font policy and the full pre-push gate passes
<!-- AC:END -->
