---
id: TASK-114
title: Treat Archive as a label rather than a system role
status: Done
assignee: []
created_date: '2026-09-27 07:42'
updated_date: '2026-09-27 07:52'
labels:
  - bug
dependencies:
  - TASK-26
priority: high
ordinal: 3500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The archive role has no consumer beyond its sidebar entry and role:archive search, and it does not mean one thing across providers: Gmail archives by removing INBOX and adds no label, so role:archive never finds archived Gmail mail, while on IMAP Archive is a folder the owner filed into. In ownmail all owned mail is archived, so a server Archive folder is one filing place among others.

Keeping it as a role also produces two sidebar entries named Archive when a Gmail label called Archive (a user label since TASK-26) sits beside an IMAP Archive folder. Gmail reserves Inbox, Sent, Drafts, Spam and Trash as label names, so Archive is the realistic clash.

Remove the role. Archive folders and labels then appear under Labels by their raw names, and one label:"Archive" entry covers both. Live IMAP sync must keep treating the \Archive SPECIAL-USE attribute as known, or messages in such folders become uncertain and are never captured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The sidebar never shows two entries named Archive; IMAP Archive folders and Gmail Archive labels appear under Labels by raw name
- [x] #2 role:archive is reported as an unknown role, and search help no longer lists it
- [x] #3 Messages in an IMAP folder advertising \Archive remain eligible for live capture
- [x] #4 Archive folders are still downloaded and still contribute their name as a label
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 14ad6dc. Remove ARCHIVE from roles (constant, ROLES, SPECIAL-USE map, name table). Add \archive to live_imap's non-state attributes so such folders stay eligible. Drop the sidebar role entry and help row. Move TASK-26 tests that used Archive as the collision example to Junk. Update doc-7 and doc-9.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed ARCHIVE from roles.py (constant, ROLES, SPECIAL-USE map, name table), its sidebar entry, help row and now-unused icon.

Evidence per AC:
- #1: an IMAP Archive folder and a Gmail Archive label give no role count and no system label, and one label count of 2 (test_archive_is_one_label_across_accounts).
- #2: parse_query('role:archive') reports Unknown role (test_query); help no longer lists it.
- #3: \archive added to live_imap._NONSTATE_ATTRIBUTES. Without it an \Archive folder counted as an unknown attribute, so its mail became uncertain and was never captured. test_imap_archive_attribute_leaves_mail_eligible fails when the entry is removed.
- #4: an \Archive folder is still a download folder and a label source, with no role (test_archive_folders_are_downloaded_and_label_mail).

TASK-26 tests that used Archive as the collision example now use Junk. Live-sync fixtures that used roles.ARCHIVE for filed mail now use an empty role set, which is what filed mail reports.

Labels added in ownmail that match a role name (e.g. 'Sent' on a Gmail message) can still create a same-name sidebar entry. The user chose to handle that later with label-management rules in ownmail, so no task was filed.
<!-- SECTION:NOTES:END -->
