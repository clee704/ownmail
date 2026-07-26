---
id: TASK-5.1
title: Design and build label-based navigation in the web UI
status: Done
assignee: []
created_date: '2026-07-24 04:54'
updated_date: '2026-07-26 03:47'
labels: []
milestone: m-3
dependencies: []
parent_task_id: TASK-5
priority: medium
ordinal: 11
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the hardcoded 'All Mail'/'Trash'-only sidebar with real label browsing: list labels (from email_labels table) with counts, let the user filter/navigate by label, decide sort order (lexicographic vs. frequency vs. configurable per ROADMAP's original note). Needs a UX decision on how labels combine with search (a label click should probably compose with the existing label: search syntax rather than being a separate code path) and how multi-valued labels per email are represented in list/detail views (currently just a raw comma-separated list, see get_labels_for_email in database.py).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sidebar shows real labels with per-label email counts, not just All Mail/Trash
- [x] #2 Clicking a label filters the email list consistently with the existing label: search syntax
- [x] #3 System labels display under one canonical name per role (roles.role_for_label, doc-7) regardless of which provider they came from, without losing the raw provider label for search
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design recorded in doc-9. Landed in three commits: the role: filter and
label counts (996409d), parse-error visibility (8343c2a, TASK-23), then
the sidebar itself (4e4c07f).

**AC #3 forced a new query term.** One entry named "Sent" has to mean "any
label whose role is sent", and label: cannot express a set union — an
archive with a Gmail API source and an IMAP source spells it SENT and
[Gmail]/Sent Mail. So role:<slug> was added over the closed set in
roles.py, resolving at search time to whichever labels this archive holds.
Reading AC #2 ("consistently with the existing label: search syntax") as
satisfied: role: composes in the same search box, lands in the same q
parameter, and is documented in the same help table. The raw label stays
searchable via label:, which is the rest of AC #3.

**Counts are a promise about result rows**, so they apply search()'s
implicit trashed_at/email_date filters. The obvious single join costs
330ms on a 100k-email archive and the sidebar renders on every page, so
get_label_counts() is a covering-index scan minus a trashed-rowid
correction (23ms, identical answer). get_role_counts() can't sum those —
a message carrying both spellings of sent is one sent message — so it
COUNT(DISTINCT)s over an inline label->role VALUES join.

**Three bugs found and filed rather than absorbed:**
- TASK-21: label:A OR label:B silently ANDs; label:A label:B silently
  drops A. role: deliberately doesn't repeat this — its filters
  accumulate in a list.
- TASK-22: FTS + label + date binds params in the wrong order, in both
  code paths. Reproduced.
- TASK-23: parse errors were never displayed anywhere. Fixed here,
  because role:'s "Unknown role" message would otherwise have been dead
  code the moment it was written.

**Decisions taken without a knob:** user labels sort lexicographically
(frequency order reshuffles on every sync); no labels in the list view
(scan-and-pick surface, and a join per page); flat hierarchy; role all
omitted from the nav; role trash named "Trash (server)" against the local
bin. Rationale for each is in doc-9.

**Verified in a running server** against a seeded two-provider archive,
light and dark, expanded and collapsed: Sent (3) returns both Gmail SENT
messages plus the one [Gmail]/Sent Mail message. Sidebar widened
140->180px because CATEGORY_PROMOTIONS and CATEGORY_UPDATES both
truncated to "CATEGORY..." at the old width.

tests/conftest.py gained mock_archive_db() — the context processor needs
real dicts from the db, and 176 test sites were repeating the same inline
MagicMock setup.
<!-- SECTION:NOTES:END -->
