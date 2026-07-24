---
id: TASK-9
title: Email export (ownmail export --format mbox|pdf)
status: To Do
assignee: []
created_date: '2026-07-24 20:29'
labels: []
milestone: m-4
dependencies: []
priority: medium
ordinal: 50
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's unscheduled Backlog section. Sketched there as:

    ownmail export --format mbox --output backup.mbox
    ownmail export --format pdf --query "from:important@example.com"

Export archived emails out of ownmail, filtered by the existing search query syntax (query.py already parses from:/subject:/attachment: etc., so --query should reuse it rather than growing a second filter language). mbox is the straightforward case - stdlib mailbox module, and it's the format other clients import. PDF is a much bigger lift (HTML-to-PDF rendering, a new heavyweight dependency) and is worth splitting into its own task or dropping unless there's a concrete need; the Minimal dependencies invariant argues against pulling in a browser engine for it.

Scope is undecided: mbox-only first is the sensible cut.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ownmail export --format mbox --output <file> writes a valid mbox importable by another client
- [ ] #2 --query filters the export using the existing search syntax, not a new one
- [ ] #3 PDF export is either implemented, split into its own task, or explicitly dropped with the reason recorded
<!-- AC:END -->
