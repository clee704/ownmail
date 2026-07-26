---
id: TASK-25
title: Reconcile an existing archive against the current download filter
status: To Do
assignee: []
created_date: '2026-07-26 05:30'
updated_date: '2026-07-26 06:12'
labels: []
dependencies: []
priority: high
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The download filter (TASK-14.1) decides what enters the archive. It says nothing about what is already in there. Any change to it — a bug fix, or a user editing their config — leaves the archive holding messages the filter would now reject, and ownmail has no way to act on that.

A standing capability, not a migration. Two consumers, both concrete:

1. **The historical exclusion bug.** Before role-based exclusion (doc-7), folders were excluded by literal name against a Gmail-only list (DEFAULT_EXCLUDE_FOLDERS = ['[Gmail]/Trash', '[Gmail]/Spam']). On a server naming its trash anything else, that folder was both a download source and a label source, so mail deleted in a client got archived as normal mail, carrying a trash-role label and — where that folder was its only source — nothing else. Fixed for future syncs; still on disk for archives synced before the fix.

2. **Any narrowing filter edit, forever after.** TASK-14.1 makes part of the filter user-editable, so this recurs by design. Someone who ran with inbox in the download set — wanting an eager mirror — and later switches to capture-at-filing is in exactly the state above, with no bug involved. Same for a named folder or label they stop wanting.

Note the configurable part is inbox, drafts and named folders/labels only. TASK-14.1 fixes trash and spam as permanently excluded, so consumer 2 never involves them.

## Shape

Reconcile is the mirror of purge (TASK-14.2), against the same filter:

| | Sweeps | For | Action |
|---|---|---|---|
| purge | the server | mail that passes the filter and is safely archived | trash the server copy |
| reconcile | the archive | mail that no longer passes the filter | move to ownmail's bin |

Naming them as a pair is the point — one filter, evaluated in both directions. That is also the argument against a one-off script: the script would be deleted after one use, and consumer 2 would rebuild it.

## Why the bin, and not a delete

verify already finds these (doc-7 AC #6, commands.py:1044) and deliberately stops at reporting, because moving user email files is a STOP item and the match is heuristic — a --fix that deleted could destroy correctly-archived mail on a false positive.

Pointing it at ownmail's own bin resolves that. The bin already exists with trash / restore / delete-forever (web.py:1912-1958, doc-8 'Status'). A moved message stays on disk and stays restorable; the operator reviews and empties it. Reversible, so not a delete, so not a STOP item.

## Accepted imprecision

Reconcile cannot be as precise as the filter it mirrors. The filter reads live server state; reconcile has only the labels stored at capture, so it is a heuristic over a snapshot (doc-7's accepted cost). That is not a flaw to engineer away — it is exactly why the destination has to be recoverable.

It also bounds what reconcile can find: only messages whose excluded role was *recorded* as a label at capture. Both consumers above satisfy that, which is why they are the two listed.

## Design points to settle

- Opt-in and explicit. Not part of verify's default run, and not implied by --fix. A separate verb or an explicit flag, so nothing moves mail as a side effect of a health check.
- Dry-run first, listing exactly what would move — consistent with doc-6's dry-run-by-default stance for purge.
- Scope the match. Only messages whose ONLY labels resolve to an excluded role are unambiguous. A message carrying user labels alongside one was captured elsewhere and later re-snapshotted, or the label is a false positive; report those separately rather than sweeping them in.
- Read the exclusion set from config, not from a hardcoded trash/spam pair — that is what makes consumer 2 work.

## Also in scope: stale labels on messages that legitimately stay

Distinct from the above and much smaller. Arrival-driven capture (the state TASK-14.3 fixes) downloaded mail while it was still in the inbox, so those messages carry an INBOX label nothing ever refreshes. Real mail, correctly archived; only the label is stale. No new ones appear once TASK-14.3 lands, but the existing ones leave a phantom Inbox entry in the sidebar whose count means 'was in the inbox when downloaded', not 'is in the inbox'.

Handle it the way TASK-5.3 handled UNREAD: hide at read, rewrite nothing. Same for a stored DRAFT label.

Keep that hiding NARROW — exact-match Gmail system label IDs (INBOX, DRAFT), never case-folded name matching. roles.role_for_label is heuristic on a stored string, and a name-based rule would hide a user label legitimately called 'Archive' or 'Trash'. See TASK-26, which is that failure already happening in the sidebar.

Do not extend the hiding to trash/spam labels: reconcile reads exactly those stored labels, so hiding them would blind the sweep this task is built on.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A dry-run reports which archived messages the current configured exclusion set would reject, with counts by label and account
- [ ] #2 The exclusion set is read from config, so a filter edit changes what reconcile reports without a code change
- [ ] #3 An explicit, opt-in action moves those messages to ownmail's local bin rather than deleting them, and they are restorable
- [ ] #4 Nothing moves as a side effect of a plain verify run
- [ ] #5 Messages carrying non-role labels alongside an excluded-role label are reported separately and not swept in
- [ ] #6 A stale INBOX or DRAFT label no longer produces a sidebar entry, with nothing rewritten on disk
- [ ] #7 A user label named 'Archive' or 'Trash' is not hidden by that rule
<!-- AC:END -->
