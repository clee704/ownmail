---
id: TASK-25
title: No supported way to act on verify's trash/spam pollution report
status: To Do
assignee: []
created_date: '2026-07-26 05:30'
updated_date: '2026-07-26 05:32'
labels: []
dependencies: []
documentation:
  - >-
    backlog/docs/doc-10 -
    Roles-are-a-pre-capture-vocabulary-—-what-the-archive-inherits-at-the-handoff.md
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

ORDERING CONSTRAINT with TASK-24 (eligibility roles): the report reads STORED labels, so its read-time hiding must not blind it. Whichever lands first, the other must not regress it.

Generalizes beyond the historical bug: the same reconciliation answers 'my download filter changed and the archive holds messages it would now reject'. Worth building it in those terms rather than as a one-off migration, since TASK-14.1 makes the filter user-editable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A dry-run reports which archived messages the current role-based exclusion would have rejected, with counts by label and account
- [ ] #2 An explicit, opt-in action moves those messages to ownmail's local bin rather than deleting them, and they are restorable
- [ ] #3 Nothing moves as a side effect of a plain verify run
- [ ] #4 Messages carrying non-role labels alongside a trash/spam label are reported separately and not swept in
- [ ] #5 verify's existing report still works after TASK-24's read-time hiding lands
<!-- AC:END -->
