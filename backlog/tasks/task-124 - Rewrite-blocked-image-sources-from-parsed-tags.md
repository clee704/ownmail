---
id: TASK-124
title: Rewrite blocked image sources from parsed tags
status: To Do
assignee: []
created_date: '2026-09-30 03:15'
labels:
  - ui
dependencies: []
priority: high
type: bug
ordinal: 9650
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_hide_blocked_images (ownmail/web.py) finds img and source tags by matching IMAGE_TAG_RE against the sanitized HTML string, the approach TASK-120 removed from _extract_body_content. The pattern does not skip quoted attribute values, so image-tag text that the sanitizer keeps inside another element's attribute is matched and rewritten as if it were a tag: IMAGE_TAG_RE.findall('<p title="<img src=a.png>">x</p>') returns one match. The sanitizer's serializer leaves < and > unescaped in attribute values, so such text reaches this function, which runs whenever remote content is blocked, before body extraction.

Found while auditing TASK-120. At minimum the rewrite alters attribute text the sender wrote; whether it can also change the element structure the browser sees has not been checked. Rewrite from parsed tags, as _MessageBodyParser does, so only real img and source elements change, and keep serialized markup intact rather than reserializing through lxml.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Image-tag text inside an attribute value is left unchanged, while real img and source elements still get the placeholder and lose remote srcset values as before
- [ ] #2 A regression test through the real sanitizer and message route shows attribute text containing image markup reaching the page unchanged with remote content blocked, and real remote images staying unrequested
- [ ] #3 The full pre-push gate passes
<!-- AC:END -->
