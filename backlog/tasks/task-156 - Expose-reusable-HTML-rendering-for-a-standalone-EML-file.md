---
id: TASK-156
title: Expose reusable HTML rendering for a standalone EML file
status: In Progress
assignee: []
created_date: '2026-11-11 20:10'
updated_date: '2026-11-11 21:37'
labels: []
dependencies: []
priority: medium
type: task
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A caller needs to preview an original MIME message stored outside the ownmail archive. The renderer shared by Print and PDF export lives in a private export helper and has no standalone entry point. Expose the existing sanitized message document renderer for one local EML file or stdin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Print, PDF export and standalone rendering use the same message document renderer.
- [x] #2 The standalone command emits HTML for one EML without archive configuration or server access. It blocks remote resources, preserves safe inline content, and reports sanitizer failure.
- [x] #3 Synthetic tests verify the standalone entry point, plain and HTML messages, sanitization, and unchanged Print and PDF behavior.
- [x] #4 Standalone rendering supports a per-document image opt-in and a query-only viewer control. Script, stylesheet, font, and media requests remain blocked.
- [x] #5 The image control uses OwnMail's image-banner styling in both modes and has a 44-pixel tap target and visible keyboard focus.
- [ ] #6 Python callers can render sanitized MIME content from bytes and supply their own document and image controls. The API works from the installed package without loading the archive web app.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Move the existing document renderer into ownmail/message_render.py, update Print and PDF callers, add ownmail render before archive initialization, and document and test the interface.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Next action: extract the shared message document renderer and exercise the new standalone command with a synthetic MIME message.

Reviewed the complete diff against the Print and PDF paths. The 60 focused rendering and export tests and the full pre-push gate passed. Verified the standalone command through a separate transaction document viewer using a synthetic EML.

2026-11-11 follow-up. A receipt viewer needs to offer Load images from the original EML. Add an explicit image-only rendering mode and an optional local toggle link using the shared standalone document template. The original Print and PDF callers retain their existing options.

The standalone preview offers a local Load images or Block images link when the message has remote content. The opt-in widens only img-src. Focused rendering, Print and PDF tests, the pre-push gate, a synthetic WebKit check, and independent review passed.

The standalone image control inherited the browser's blue, underlined link style. Applied the archive image banner palette. A synthetic receipt passed the mobile WebKit checks for both modes and the desktop WebKit keyboard focus check. The full pre-push gate passed.

The CLI currently couples the consumer to the installed executable and the Print page. Extract a content API in the rendering module and share MIME and HTML helpers with the archive reader.

Next action: move the shared content helpers out of the web app and reuse them in the installed rendering API.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Extracted the existing printable message renderer for Print, PDF export, and the new ownmail render command. The command reads an original EML file or stdin and returns sanitized offline HTML without starting an archive.

Standalone EML previews now support a per-document remote image choice with the existing HTML sanitizer and a local toggle link.
<!-- SECTION:FINAL_SUMMARY:END -->
