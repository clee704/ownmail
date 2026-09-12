---
id: TASK-32.4
title: Improve message reading layout and return to results
status: To Do
assignee: []
created_date: '2026-09-12 18:33'
labels:
  - ui
  - ux
dependencies:
  - TASK-32.1
parent_task_id: TASK-32
priority: medium
ordinal: 4
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make a message readable and let the reader return to the same result list. Message links currently contain only the email ID. The detail template has no search bar or explicit return-to-results control, and the trash action falls back to document.referrer. Subject, full recipient details, labels and actions compete for space above the body.

Apply TASK-32.1's styles to the message header, body container, image banner and attachments. Provide explicit navigation preserving the originating query, sort and page, with list position restored when returning in the same tab. Use a safe local fallback for direct links. Keep message actions discoverable and distinguish routine reading actions from destructive ones. This covers individual-message reading; conversation grouping remains TASK-6. Sanitization, external-image policy and archive mutations retain their existing behavior.

Evidence: ownmail/templates/_email_list.html, email.html and base.html; ownmail/web.py message route and back-to-search helper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An explicit Back to results control preserves query, sort and page; returning in the same tab restores list position, and direct message links have a safe local fallback.
- [ ] #2 Long subjects, recipient lists and label sets fit without obscuring the body or action controls; secondary metadata remains accessible.
- [ ] #3 Plain-text messages, wide HTML messages and attachment lists remain readable at narrow/wide widths in light/dark mode, with app styles kept separate from authored email content.
- [ ] #4 Existing image-loading choices, attachment preview/download and original-message access remain discoverable and functional; validation records synthetic examples and navigation checks.
<!-- AC:END -->
