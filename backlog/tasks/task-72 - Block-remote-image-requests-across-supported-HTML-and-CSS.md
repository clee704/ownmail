---
id: TASK-72
title: Block remote image requests across supported HTML and CSS
status: To Do
assignee: []
created_date: '2026-09-13 20:20'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The README review confirmed that rendered messages can retain active CSS image URLs and responsive image sources while image blocking is enabled. A synthetic message passed through the real sanitizer and Flask message route retains these sources, with no message-response CSP preventing requests. The blocked-images banner can therefore overstate the protection. Correct the blocking behavior without changing archived messages or weakening HTML sanitization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With image blocking enabled and an untrusted sender, browser tests confirm that supported HTML and CSS image sources make no remote requests.
- [ ] #2 Explicitly loading images and trusting a sender restore intended image behavior; blocked-state feedback accurately describes the result.
- [ ] #3 Regression cases include style-block images and responsive image sources, and the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Found during TASK-69 documentation review using synthetic input only. No real archive or credentials were accessed, and no outbound image requests were sent. Documentation qualifies the existing limitation pending this fix.
<!-- SECTION:NOTES:END -->
