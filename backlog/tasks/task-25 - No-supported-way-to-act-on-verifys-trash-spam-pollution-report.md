---
id: TASK-25
title: No supported way to act on verify's trash/spam pollution report
status: To Do
assignee: []
created_date: '2026-07-26 05:30'
updated_date: '2026-07-26 05:32'
labels: []
dependencies: []
priority: high
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An archive synced before role-based exclusion (doc-7) holds mail downloaded FROM a trash or spam folder that the old Gmail-only name list (DEFAULT_EXCLUDE_FOLDERS = ['[Gmail]/Trash', '[Gmail]/Spam']) failed to match. On any server naming those folders differently, the folder was both a download source and a label source, so the messages carry a trash- or spam-role label and, where that folder was their only source, no other label at all. This is mail its owner deleted in a client and ownmail captured by mistake.

verify already finds them — doc-7 AC #6, commands.py:1044 — and deliberately stops at reporting, because moving user email files is a STOP item and the name-table match is heuristic, so a --fix that deleted would risk destroying correctly-archived mail on a false positive.

The gap is that the report has no next step. A user who runs verify, sees the count, and agrees with every line still has nothing to do about it but move files by hand.

RESOLUTION: point the report at a destination that is reversible. ownmail already owns a local bin with trash/restore/delete-forever (web.py:1912-1958, doc-8 'Status'). Moving a flagged message there is not a delete — it stays on disk, stays restorable, and the user empties the bin themselves once they have reviewed it. That takes the action out of STOP territory while keeping the heuristic's false positives recoverable.

Design points to settle:
- Opt-in and explicit. Not part of verify's default run, and not implied by --fix. A separate verb or an explicit flag, so nothing moves mail as a side effect of a health check.
- Dry-run first, listing exactly what would move, consistent with doc-6's dry-run-by-default stance for purge.
- Scope the match. Only messages whose ONLY labels resolve to trash/spam are unambiguous pollution. A message carrying user labels alongside a trash label was captured from elsewhere and later re-snapshotted, or the label is a false positive — those need review, not bulk action, so report them separately rather than sweeping them in.
- Distinguish this from purge (TASK-14.2). Purge acts on the SERVER copy of mail ownmail holds; this acts on the LOCAL copy of mail ownmail should never have taken. Same direction, opposite side.

ALSO IN SCOPE — stale labels on messages that legitimately stay. Distinct from the messages above, and much smaller. Arrival-driven capture (the state TASK-14.3 fixes) downloaded mail while it was still in the inbox, so those messages carry an INBOX label that ownmail never refreshes. Real mail, correctly archived; only the label is stale. Once TASK-14.3 lands no new ones appear, but the existing ones keep a phantom Inbox entry in the sidebar with a count that means 'was in the inbox when downloaded', not 'is in the inbox'.

Handle it the way TASK-5.3 handled UNREAD: hide at read, rewrite nothing. Same for a stored DRAFT label.

Keep that hiding NARROW — exact-match Gmail system label IDs (INBOX, DRAFT), never case-folded name matching. roles.role_for_label is heuristic on a stored string, and a name-based rule would hide a user label legitimately called 'Archive' or 'Trash'. See TASK-26, which is that failure already happening in the sidebar.

Do not extend the hiding to trash/spam labels: verify's report reads exactly those stored labels, so hiding them would blind the report this task is built on.

Generalizes beyond the historical bug: the same reconciliation answers 'my download filter changed and the archive holds messages it would now reject'. Worth building it in those terms rather than as a one-off migration, since TASK-14.1 makes the filter user-editable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A dry-run reports which archived messages the current role-based exclusion would have rejected, with counts by label and account
- [ ] #2 An explicit, opt-in action moves those messages to ownmail's local bin rather than deleting them, and they are restorable
- [ ] #3 Nothing moves as a side effect of a plain verify run
- [ ] #4 Messages carrying non-role labels alongside a trash/spam label are reported separately and not swept in
- [ ] #5 A stale INBOX or DRAFT label no longer produces a sidebar entry, with nothing rewritten on disk
- [ ] #6 A user label named 'Archive' or 'Trash' is not hidden by that rule
<!-- AC:END -->
