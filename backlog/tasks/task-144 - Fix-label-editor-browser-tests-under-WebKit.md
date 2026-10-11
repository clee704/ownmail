---
id: TASK-144
title: Fix label editor browser tests under WebKit
status: To Do
assignee: []
created_date: '2026-10-11 22:46'
labels:
  - testing
dependencies: []
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With OWNMAIL_BROWSER_ENGINE=webkit, four tests in tests/test_label_editor.py fail on page errors (test_cached_message_markup_cannot_send_label_requests[page] and [injected-editor-script], test_editor_ignores_message_markup_when_its_own_section_is_missing, test_archive_editor_saves_its_own_labels_beside_message_markup). They pass under Chromium. Found while working on TASK-143; the failures predate it.
<!-- SECTION:DESCRIPTION:END -->
