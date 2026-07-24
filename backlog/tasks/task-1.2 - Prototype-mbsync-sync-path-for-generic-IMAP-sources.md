---
id: TASK-1.2
title: Prototype mbsync sync path for generic IMAP sources
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-07-23 19:21'
labels:
  - sync
dependencies: []
parent_task_id: TASK-1
priority: medium
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace providers/imap.py sync loop with mbsync for non-Gmail IMAP sources (Fastmail, work IMAP, legacy providers). Gmail stays on GmailProvider, not mbsync.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 mbsync config generated from ownmail config.yaml IMAP sources
- [ ] #2 Gmail sources explicitly excluded from mbsync path, continue using GmailProvider
- [ ] #3 Resulting Maildir++ layout can be indexed without breaking existing archive structure/scan logic
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reversed after implementing and discussing with the user (git revert db4bd12 reverts 6e005a4 cleanly - code removed from the branch).

Built a working prototype first (mbsync config generator + Maildir++ ingester, new CLI commands, validated against real prod .eml content and the real mbsync binary - see git history for the reverted commit if resurrecting this). On review, concluded it wasn't worth adopting:

- providers/imap.py already does everything mbsync would bring: multi-folder sync, folder-name-to-label mapping, cross-folder dedup by content hash, resumable incremental sync via sync_state. mbsync doesn't add a missing capability.
- The dual-write design (mbsync's own Maildir++ staging tree under sources/<name>/mbsync/, separate from ownmail's existing date-organized archive layout, with mbsync-ingest copying between them) means two on-disk layouts and two copies of synced mail per IMAP account - complexity the user did not want to take on.
- No concrete IMAP-provider pain point (bug, fragility, missing feature) motivated this - it was speculative, like the notmuch task (TASK-1.5).
- The main genuine upside (mature battle-tested protocol handling vs. custom imaplib code) is real but only worth the dependency + layout cost if/when a concrete problem with imap.py shows up in practice.

Go/no-go: NO-GO on adopting mbsync. Revisit only if providers/imap.py hits a real, specific problem (a server it can't handle, a bug, a missing feature) that's cheaper to solve via mbsync than by fixing imap.py directly.
<!-- SECTION:NOTES:END -->
