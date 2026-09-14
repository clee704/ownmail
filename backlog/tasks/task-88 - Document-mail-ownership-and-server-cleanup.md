---
id: TASK-88
title: Document mail ownership and server cleanup
status: Done
assignee: []
created_date: '2026-09-14 08:52'
updated_date: '2026-09-14 08:59'
labels: []
dependencies: []
type: docs
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Write a concise product document explaining why ownmail preserves mail locally, keeps mail clients useful for live messages, and provides a consolidated reading and search view. Distinguish Active downloads, permanent archival, and server cleanup; align superseded design records without implementing the planned behavior.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A concise canonical document explains the purpose, authority boundary, message states, capture timing, and thread-aware server cleanup.
- [x] #2 README links to the document, and affected design records distinguish the new direction from current implementation and superseded decisions.
- [x] #3 Documentation links and repository checks pass; the changes are committed with a clean working tree.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added docs/philosophy.md with the product purpose, Active and Archived ownership, observation-based capture, and independent server cleanup. Independent prose review found no ownership contradiction; clarified that permanent removal from provider Trash is not guaranteed by a move to Trash.

Linked the document from README, marked doc-6/doc-8 and TASK-33 as historical, and aligned TASK-14, TASK-14.2, TASK-28, TASK-38, and execution order. Removed obsolete future-purge wording from configuration comments. Active enablement defaults, cadence, presentation details, and provider handling of unfinished outgoing mail remain implementation choices. No runtime behavior or configuration values changed.

All 24 local links across changed Markdown resolve. Independent integration review found no remaining operative design contradictions, dependency cycle, or runtime changes. pre-commit run -a --hook-stage pre-push passed, including the full suite and coverage gate.

Documentation committed as 18cec0f after validation. Task completion recorded after the documentation checkpoint.
<!-- SECTION:NOTES:END -->
