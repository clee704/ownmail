---
id: TASK-14
title: Optional purge + configurable download filter
status: To Do
assignee: []
created_date: '2026-07-24 22:45'
updated_date: '2026-07-24 23:01'
labels: []
milestone: m-5
dependencies:
  - TASK-5.2
documentation:
  - >-
    backlog/docs/doc-6 -
    Email-stack-architecture-—-ownmails-role-and-the-remote-drain.md
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two orthogonal knobs that compose to give 'no mail left on third-party servers', without changing any of ownmail's current default behaviour.

KNOB 1 - PURGE (opt-in, default off)
Default stays exactly as today: ownmail reads, never deletes. When enabled, ownmail deletes a message from the server once it has confirmed the local copy is correct.

- Purge means MOVE TO TRASH, not hard delete. This is what makes 'servers own the grace period' actually work - Gmail's 30-day Trash retention is the grace period, and ownmail implements no time logic at all. It also composes with knob 2: the default filter excludes trash, so a message ownmail just trashed is not re-downloaded.
- Confirmation is a per-message content-hash re-check of the local .eml at purge time, via the existing verify/sync-check machinery (cli.py:809,818). Not 'synced recently, probably fine'.
- SWEEP semantics, not download-time-only. Purge considers every message on the server that passes the current filter and has a verified local copy - not just messages downloaded in this run. Download-time-only cannot meet the goal, because mail archived before purge was enabled would sit on the server forever. Consequence: the filter is evaluated LIVE against current server state at purge time, so a message downloaded a year ago while it sat in the inbox becomes purgeable the moment it is archived.
- OAuth scope: gmail.py:16 currently requests gmail.readonly. Trash needs gmail.modify (hard delete would need full https://mail.google.com/, another reason to prefer trash). Scope changes are a STOP item and force every existing token to re-consent - so readonly must remain the default and only purge users take the wider scope.

KNOB 2 - DOWNLOAD FILTER (configurable)
Which messages get downloaded at all. Purge requires download, so anything filtered out is automatically never purged - that coupling is what makes the inbox safe without a dedicated rule.

- Not new machinery: the filter already exists in three inconsistent places and none are exposed in config. imap.py:27 DEFAULT_EXCLUDE_FOLDERS is configurable but defaults to Gmail-specific folder names; gmail.py:130 hardcodes '-in:trash -in:spam'; gmail.py:224 re-checks TRASH/SPAM on labelIds. This task unifies and exposes them.
- Filter terms are CANONICAL system-label names, which is why this depends on TASK-5.2. Providers spell the same concept differently - TRASH vs Trash vs [Gmail]/Trash vs 'Deleted Items', plus IMAP SPECIAL-USE flags. A filter config cannot be written against raw provider strings.
- Default filter: exclude trash, spam, and DRAFTS. Drafts matter because they are live working state - purging them would yank an in-progress draft out from under a mail client mid-compose. This is the only default behaviour change in the task.
- Target config for the intended setup is then just: filter excludes inbox + trash (+ spam, drafts), purge on. Everything else is downloaded and trashed on the server.

HAZARD: under sweep semantics, editing the filter is a destructive action. Removing 'inbox' from the exclude list means the next purge run trashes the entire inbox. Dry-run-by-default covers most of this, but it should be called out in the config docs.

SUPERSEDES TASK-15: 'should client-side deletions reach the archive' is now just the default filter value, i.e. config rather than a code decision.

STOP ITEM: deletes user email and changes OAuth scopes. Needs explicit human sign-off before implementation and lands via PR, not straight to master.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Purge is opt-in and off by default; with it off, ownmail's behaviour is byte-for-byte what it is today
- [ ] #2 Purge moves messages to the provider's Trash rather than hard-deleting, so the provider's own retention is the only grace period; ownmail implements no time logic
- [ ] #3 A message is purged only after its local .eml is re-hashed at purge time and matches the recorded content hash
- [ ] #4 Purge sweeps all server messages passing the current filter, not only those downloaded in the current run
- [ ] #5 The filter is evaluated live against server state at purge time, so triage changes take effect on the next run
- [ ] #6 Download filter is configured with canonical system-label names (per TASK-5.2), not raw provider folder strings
- [ ] #7 The three existing filter sites (imap.py:27, gmail.py:130, gmail.py:224) are unified into one mechanism, with no provider-specific defaults left hardcoded
- [ ] #8 Default filter excludes trash, spam and drafts; drafts exclusion is verified to leave in-progress drafts untouched on the server
- [ ] #9 Dry-run is the default for purge: reports what would be trashed, per account, and changes nothing
- [ ] #10 Verification failure or a missing local file skips that message and reports it; it never aborts the run
- [ ] #11 Purge is resumable and batch-committed - Ctrl-C leaves consistent state (invariant 3)
- [ ] #12 config.example.yaml documents both knobs, and warns that narrowing the filter makes the next purge run delete more
- [ ] #13 Confirmed whether mailbox.org offers a Trash retention window like Gmail's 30 days; documented either way
- [ ] #14 OAuth scope change from gmail.readonly signed off separately, with a documented re-consent path for existing tokens
- [ ] #15 Human sign-off recorded and the work landed via PR, not direct to master
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Filter resolution must be semantic, not name-based.** Provider system folders/labels differ in more than spelling: IMAP INBOX is a folder (one location per message) while Gmail INBOX is a label (carried alongside others, with the message living in All Mail either way); IMAP names are case-insensitive per RFC 3501; Gmail-over-IMAP puts the same message in INBOX and [Gmail]/All Mail at once (imap.py:236 downloads from All Mail as sole source for exactly this reason); and folder names are localized — imap.py:211-219 hardcodes four language variants of All Mail and misses many others.

So the filter must resolve a per-message *role* (JMAP's model; what IMAP SPECIAL-USE advertises as \\Trash, \\Junk, \\Drafts) per provider, not match folder-name strings. This is why the TASK-5.2 dependency is a correctness precondition rather than presentation polish — see doc-6.
<!-- SECTION:NOTES:END -->
