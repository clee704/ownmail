---
id: TASK-24
title: Stop inheriting eligibility roles as archive labels
status: To Do
assignee: []
created_date: '2026-07-26 05:29'
labels: []
dependencies: []
documentation:
  - >-
    backlog/docs/doc-10 -
    Roles-are-a-pre-capture-vocabulary-—-what-the-archive-inherits-at-the-handoff.md
priority: high
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implements doc-10. Roles split along the capture event: inbox/trash/spam/drafts/archive/all are read by the download filter and folder discovery BEFORE capture, while sent is the only one durably true of the message afterwards. doc-8 says ownmail never re-reads server label state after capture, so a stored eligibility role is a frozen snapshot of a state whose nature is to change, with nothing able to correct it — the same argument TASK-5.3 made for read/unread.

Consequence: an archive should never carry an inbox-, trash-, drafts-, archive- or all-role label, whether or not the download filter admitted the message. Widening the filter to capture client-side deletions (doc-6's TASK-15 resolution) stays supported; those messages just land as ordinary archived mail, which is what choosing to keep them means.

TWO HALVES, DIFFERENT TESTS — this is the load-bearing detail:

1. GOING FORWARD, drop at the handoff from LIVE provider state. Extend the mechanism that already drops UNREAD in _resolve_label_names (gmail.py:392). The test cannot be a literal name list (IMAP spellings vary), so it is the role — resolved while the good signal is still available: exact Gmail label IDs, or the IMAP folder scan's SPECIAL-USE flags and reported delimiter.

2. EXISTING ARCHIVES, hide at read, and only where the raw string is unambiguous. All the archive kept is the label text, so role_for_label is heuristic (doc-7's accepted cost) and a blanket hide would swallow a user label legitimately named 'Archive', 'Trash' or 'Bin' — see TASK-26, which is that failure already happening. Restrict the read-time rule to exact-match Gmail system label IDs (INBOX, TRASH, SPAM, DRAFT), never case-folded, on the same reasoning EPHEMERAL_LABELS documents for UNREAD.

Neither half rewrites a sidecar.

SIDEBAR FALLOUT (revises doc-9): the system-roles section collapses to Sent. Four roles can no longer occur, 'all' was already hidden, and 'spam' is opt-in-only pending TASK-19. _ROLE_NAMES' 'Trash (server)' disambiguation goes away with it — with no trash-role label in the archive there is no collision, and 'Trash' in the UI unambiguously means ownmail's own bin. role: remains a valid search term for every role; a role: search that can no longer match correctly returns nothing.

SPAM IS NOT DECIDED HERE. It is a classification rather than a location, which is the category TASK-19 already owns (IMPORTANT, CATEGORY_*, STARRED). Low stakes — the default filter excludes spam.

ORDERING CONSTRAINT with TASK-25: verify's pollution report reads STORED labels. Hiding eligibility roles at read time must not blind it, or the cleanup path loses its input.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Labels resolving to an eligibility role are not written at capture, on both the Gmail API and IMAP paths, resolved from live provider state rather than from the stored string
- [ ] #2 sent is still inherited; spam is left as-is pending TASK-19
- [ ] #3 Read-time hiding is limited to exact-match Gmail system label IDs and does not hide a user label whose name merely looks like a system folder
- [ ] #4 The sidebar's system section renders Sent (and Spam where present) and no longer offers Inbox, Drafts, Archive or 'Trash (server)'
- [ ] #5 verify's trash/spam report still sees the labels it reports on (TASK-25 ordering constraint)
- [ ] #6 doc-9's sidebar structure and _ROLE_NAMES are updated to match, with doc-10 cited as the revision
<!-- AC:END -->
