---
id: TASK-14
title: Drain remote servers — delete archived mail once verified locally
status: To Do
assignee: []
created_date: '2026-07-24 22:45'
labels: []
milestone: m-5
dependencies: []
documentation:
  - >-
    backlog/docs/doc-6 -
    Email-stack-architecture-—-ownmails-role-and-the-remote-drain.md
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Net-new capability from doc-6: once a message is archived locally and verified, delete it from the remote server, so no mail is left on third-party servers long-term.

One policy rule and one precondition (they are different kinds of thing):

- POLICY - skip anything currently in INBOX. Age is the wrong predicate. The inbox is a decision queue kept near-empty, so a message still in it is undecided at any age, and one that has been archived is decided. Triage is already the signal. This is the only user-facing rule.
- PRECONDITION - the local .eml must verify by content hash before expunging. No knob, never surfaced, but it is the difference between a drain and data loss. Per-message check at drain time via the existing verify/sync-check machinery (cli.py:809,818), not 'synced recently, probably fine'.

Read INBOX membership LIVE from the server in the same session that does the delete. That is what makes a grace period unnecessary - the only thing a delay protects against is a stale local view of where a message lives, and there is nothing stale about state read immediately before expunging.

Explicitly out of scope as speculative (see doc-6): exempting flagged/starred messages, a 'keep' hold label, any grace period or age threshold, and the stale-inbox report.

No dependency on TASK-5.2: INBOX is the one system folder standardized across both providers (IMAP mandates it, Gmail has a native INBOX label), so it needs no canonical mapping. Note providers/imap.py is pull-only today - it has no STORE/EXPUNGE path at all.

STOP ITEM: this deletes user email. Needs explicit human sign-off before implementation and lands via PR, not straight to master.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dry-run is the default: reports exactly what would be deleted, per account, and deletes nothing
- [ ] #2 A message is eligible only if it is not in INBOX on the server, read live in the same session as the delete
- [ ] #3 A message is expunged only after its local .eml is re-hashed and matches the recorded content hash
- [ ] #4 Verification failure or a missing local file skips the message and reports it; it never blocks the rest of the run
- [ ] #5 Drain is resumable and batch-committed - Ctrl-C leaves consistent state (invariant 3)
- [ ] #6 Confirmed whether mailbox.org offers a Trash recovery window like Gmail's 30-day one; documented either way
- [ ] #7 Human sign-off recorded and the work landed via PR, not direct to master
<!-- AC:END -->
