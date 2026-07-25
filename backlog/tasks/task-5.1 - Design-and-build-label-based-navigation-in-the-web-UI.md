---
id: TASK-5.1
title: Design and build label-based navigation in the web UI
status: To Do
assignee: []
created_date: '2026-07-24 04:54'
updated_date: '2026-07-25 05:24'
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
- [ ] #1 Sidebar shows real labels with per-label email counts, not just All Mail/Trash
- [ ] #2 Clicking a label filters the email list consistently with the existing label: search syntax
- [ ] #3 System labels display under one canonical name per role (roles.role_for_label, doc-7) regardless of which provider they came from, without losing the raw provider label for search
<!-- AC:END -->
