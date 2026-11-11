---
id: TASK-156
title: Expose reusable HTML rendering for a standalone EML file
status: Done
assignee: []
created_date: '2026-11-11 20:10'
updated_date: '2026-11-11 20:20'
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
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Move the existing document renderer into ownmail/message_render.py, update Print and PDF callers, add ownmail render before archive initialization, and document and test the interface.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Next action: extract the shared message document renderer and exercise the new standalone command with a synthetic MIME message.

Reviewed the complete diff against the Print and PDF paths. The 60 focused rendering and export tests and the full pre-push gate passed. Verified the standalone command through a separate transaction document viewer using a synthetic EML.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Extracted the existing printable message renderer for Print, PDF export, and the new ownmail render command. The command reads an original EML file or stdin and returns sanitized offline HTML without starting an archive.
<!-- SECTION:FINAL_SUMMARY:END -->
