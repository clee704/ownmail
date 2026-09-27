---
id: TASK-26
title: role_for_label misreads user labels named like system folders
status: Done
assignee: []
created_date: '2026-07-26 05:31'
updated_date: '2026-09-27 06:43'
labels:
  - bug
dependencies: []
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
roles.role_for_label() resolves a STORED label string by trying the Gmail label-ID map, then the IMAP leaf-name table under both hierarchy delimiters. The name table is case-insensitive and matches on the leaf, so any user label whose name happens to collide with a system-folder spelling resolves to that role.

Confirmed in a real archive. Synthetic example: a user label 'Archive' (with a child 'Archive/Example') resolves to role archive. The consequences are all in the post-capture read paths:

- _build_label_nav (web.py) skips any label with a truthy role_for_label, so 'Archive' vanishes from the user-label list and is folded into the system Archive entry — while its child 'Archive/Example' stays under user labels, because the leaf 'Example' matches nothing. One label tree, split across two sections, with the parent renamed.
- _label_chips (web.py) renames the chip to the role's display name and links it to role:archive instead of label:"Archive".
- A role: search resolves the union of every label with that role, so role:archive returns the user label's messages.

The table's false-positive surface is wide: 'Trash', 'Bin', 'Drafts', 'Sent', 'Home' near-misses, and every localized spelling in _FOLDER_NAMES. Gmail user labels are freely named, so collisions are expected rather than exotic.

WHY THIS IS NOT JUST doc-7'S ACCEPTED COST: doc-7 accepted that a folder identifiable only by SPECIAL-USE cannot be re-resolved offline — a FALSE NEGATIVE, and it argued the case was narrow because such folders are excluded at sync time so the message never lands. This is the opposite direction: a false POSITIVE on a label that is legitimately in the archive, in a read path doc-7 was not reasoning about.

Approach to weigh: at capture the provider signal is unambiguous (exact Gmail label IDs; SPECIAL-USE flags plus the reported delimiter), and only the post-capture read paths are guessing. Options include restricting role_for_label's name-table branch to labels that came from a folder-shaped source, recording the resolved role at capture (doc-7 notes a sync_state cache needs no schema change), or narrowing the read paths to exact Gmail system label IDs the way EPHEMERAL_LABELS already does.

TASK-25's stale-label hiding avoided the heuristic by matching STALE_STATE_LABELS exactly, but reconcile did not. SourceFilter.rejects and classify in ownmail/reconcile.py call role_for_label, so on a source that excludes trash or spam, a message whose only label is a user label named 'Trash', 'Bin', or 'Junk' is classified as rejected with nothing kept, and reconcile --apply moves it to the local bin, which expires after 30 days. The trash/spam label report in commands.py uses the same heuristic. This makes the defect a data-loss risk, not only a display one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A user label whose name collides with a system-folder spelling stays in the user-label section under its own name
- [x] #2 Its chip links to label:"<raw>", not to role:<slug>
- [x] #3 A role: search does not return messages whose only matching label is a user label
- [x] #4 Genuine provider system labels still resolve to their role
- [x] #5 reconcile does not sweep a message whose only matching label is a user label that shares a system-folder name
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 0866463.

Resolve stored labels per account kind. Gmail accounts (gmail_api, or imap on imap.gmail.com) name system labels unambiguously: API IDs, or folders under [Gmail]/ or [Google Mail]/. Every other Gmail label string is the user's own, so the bare-name table no longer applies to them. Generic IMAP accounts and accounts missing from config keep the name-table fallback, since a bare folder name is the only evidence there.

1. roles.role_for_label takes a required gmail flag.
2. config.gmail_accounts(config) derives the Gmail account set.
3. reconcile SourceFilter and the verify trash/spam report resolve per account.
4. ArchiveDatabase takes gmail_accounts; role search, role counts and a system-label set resolve generic-only labels only for non-Gmail accounts.
5. Web chips resolve with the email's account; the sidebar keeps a label in the user section when any Gmail account holds it.

No schema or sidecar change; roles stay derived (doc-7).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Stored labels now resolve per account kind. config.gmail_accounts() marks gmail_api sources and imap sources on imap.gmail.com. On those accounts only Gmail API label IDs and folders under [Gmail]/ or [Google Mail]/ have a role. Generic IMAP accounts and accounts missing from config keep the leaf-name table.

Chosen over recording roles at capture because config already identifies the provider, so existing archives are fixed with no re-sync and no persisted state (doc-7's derive-on-demand rule holds). No schema or sidecar change.

Evidence per AC:
- #1: DB get_system_labels() keeps a label Gmail holds out of the system-only set; the sidebar lists it by raw name (test_web TestLabelSidebar).
- #2: chips resolve with the message's account (test_gmail_user_label_chip_keeps_its_name).
- #3: role: search and role counts restrict name-table-only labels to non-Gmail accounts, in the archive and the Active cache (TestGmailUserLabelsNamedLikeFolders, test_active_search).
- #4: TRASH, [Gmail]/Trash and [Google Mail]/Bin still resolve on Gmail; generic IMAP 'Archive' still resolves.
- #5: reconcile SourceFilter carries the account kind; a Gmail message labelled only 'Trash' is neither swept nor reported (test_a_gmail_user_label_named_like_trash_is_never_swept). The verify trash/spam report uses the same rule.

Remaining limits, by design: on a generic IMAP server a user folder named like a system folder still resolves, since the name is the only evidence; the same holds for a locally added label on such a message. A label held by both a Gmail account and a generic IMAP account appears in both sidebar sections, and its label: count spans both accounts, as label: search does.

get_labels_for_role was replaced by _role_match; it had no other callers. Reconcile command test fixtures moved from gmail_api to a generic IMAP source because they put 'Deleted Items' on a Gmail account, which Gmail never produces.
<!-- SECTION:NOTES:END -->
