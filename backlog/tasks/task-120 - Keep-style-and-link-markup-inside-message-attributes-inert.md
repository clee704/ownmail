---
id: TASK-120
title: Keep style and link markup inside message attributes inert
status: Done
assignee: []
created_date: '2026-09-29 12:31'
updated_date: '2026-09-29 16:21'
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
- [x] #1 Style and link markup written inside attribute values stays attribute text after body extraction, and the message's real style and link elements keep their cascade order
- [x] #2 A browser test confirms that an event handler written inside an attribute this way does not run, with remote content blocked and loaded
- [x] #3 The full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 1084a8e. Collect real <style>/<link> elements with a tag-aware scan (STYLE_LINK_TOKEN_RE) that consumes each tag's quoted attribute values, so markup the sanitizer keeps as inert attribute text is left in place instead of being lifted out. Kept body content string-based (not lxml re-serialization) to avoid regressing void elements like <source>. Unit tests for the two attribute cases plus a browser test that the injected handler never runs while blocked and loaded.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed in ownmail/web.py: _extract_body_content now delegates style/link collection to _split_style_and_link_elements, which walks the markup one tag at a time (STYLE_LINK_TOKEN_RE consumes each tag's quoted attribute runs). A <link> or <style> the sanitizer keeps as inert attribute text is swallowed by its enclosing tag, so it is no longer lifted into a live element; real style/link elements keep document (cascade) order. Body content stays string-based rather than re-serialized through lxml, which would have regressed void elements such as <source> inside <picture>. Comment handling was left out because DOMPurify strips comments before this runs. Tests: two unit cases in tests/test_web.py and a browser test in tests/test_image_blocking.py asserting the injected onload/onerror never fires with remote content blocked and loaded; all three fail against the pre-fix code. Full pre-push gate green at 96.44% coverage.
<!-- SECTION:NOTES:END -->
