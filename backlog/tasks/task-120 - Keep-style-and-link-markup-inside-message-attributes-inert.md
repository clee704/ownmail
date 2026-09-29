---
id: TASK-120
title: Keep style and link markup inside message attributes inert
status: To Do
assignee: []
created_date: '2026-09-29 12:31'
labels:
  - ui
dependencies: []
priority: high
type: bug
ordinal: 9600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_extract_body_content collects a message's <style> and <link> tags by matching the sanitized HTML string, so markup that DOMPurify keeps as inert attribute text can become live elements:

- A <link> written inside an attribute value is prepended to the message as a live element with the attributes the sender wrote. An event-handler attribute on it runs when the message opens, whether or not remote content is blocked: loaded messages carry no CSP, and the blocking policy allows inline handlers because the reader uses them. Confirmed in Chromium through the real sanitizer and message route; an independent check also navigated the page to a remote host this way.
- A <style> start tag inside an attribute value pairs with a later real </style>, so the message markup and text between them become one style element.

Both reproduce with synthetic messages, and the matching predates TASK-117. Collect style and link elements from the parsed document instead of the serialized string. Removing 'unsafe-inline' from the blocking policy's script-src would also stop injected handlers while blocked, but the reader's inline scripts and handlers would have to move first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Style and link markup written inside attribute values stays attribute text after body extraction, and the message's real style and link elements keep their cascade order
- [ ] #2 A browser test confirms that an event handler written inside an attribute this way does not run, with remote content blocked and loaded
- [ ] #3 The full pre-push gate passes
<!-- AC:END -->
