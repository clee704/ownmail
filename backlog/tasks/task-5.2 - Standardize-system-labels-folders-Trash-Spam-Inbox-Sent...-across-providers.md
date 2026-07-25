---
id: TASK-5.2
title: >-
  Standardize system labels/folders (Trash, Spam, Inbox, Sent...) across
  providers
status: Done
assignee: []
created_date: '2026-07-24 04:54'
updated_date: '2026-07-25 05:25'
labels: []
milestone: m-1
dependencies: []
parent_task_id: TASK-5
priority: high
ordinal: 3
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Today, Gmail's own TRASH/SPAM labels are excluded at download time (gmail.py -in:trash -in:spam, and a TRASH/SPAM label check), and IMAP excludes '[Gmail]/Trash' and '[Gmail]/Spam' by default (imap.py DEFAULT_EXCLUDE_FOLDERS) - so ownmail's new local 'Trash' (trashed_at column, added in 9494f50) doesn't collide with a provider-native Trash today. But provider folder-naming isn't standardized: Gmail uses '[Gmail]/Trash', Outlook uses 'Deleted Items', other IMAP servers vary - so once labels get real UI visibility (see sibling task), those would show up as distinct, provider-specific labels instead of one recognizable 'Trash' concept, and a user with multiple accounts would see fragmented/duplicate-looking folders for the same real-world concept. Decide: should ownmail map known provider folder names to a small set of canonical system labels/folders (Inbox, Sent, Drafts, Trash, Spam, Archive) shown uniformly in the UI regardless of source account, while preserving the raw provider label for search/debugging? Needs a design decision, not just an implementation - open with the user before building.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Design doc/decision recorded on canonical system-label mapping (or an explicit decision not to do it)
- [x] #2 IMAP SPECIAL-USE (\Trash, \Junk, etc.) is used to detect system folders when the server advertises it
- [x] #3 Fallback default exclude list covers common non-Gmail trash/spam folder names, not just [Gmail]/Trash and [Gmail]/Spam
- [x] #4 exclude_folders documented in config.example.yaml
- [x] #5 Existing archived emails wrongly carrying a synced Trash/Spam-equivalent label are identified (verify --fix candidate?) so already-polluted archives can be cleaned up, not just future syncs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed, not just theoretical: imap.py:28 DEFAULT_EXCLUDE_FOLDERS = ["[Gmail]/Trash", "[Gmail]/Spam"] is a literal Gmail-only folder-name match. Any IMAP account whose trash folder is named anything else (plain "Trash", "Deleted Items", "INBOX.Trash", etc.) skips the exclusion entirely and gets archived as a normally-labeled email - reported by the user finding a real archived email with label "Trash".

**Resolved 2026-07-25.** Design decision recorded in `backlog/docs/doc-7 - Canonical system-label roles`. Settled with the user on three open forks:

1. **Roles are derived, never stored.** `ownmail/roles.py` is a pure function over provider state. No schema change, no sidecar version bump (`SIDECAR_VERSION` stays 1). Improving the name table retroactively fixes existing archives. Accepted cost: a folder identifiable only by SPECIAL-USE can't be re-resolved offline later.
2. **AC #6 is report-only.** No `--fix`. Moving user email files is a STOP item and the name-based match is heuristic — a user label genuinely named "Junk" is indistinguishable from a real junk folder.
3. **`exclude_folders` keeps replace semantics.** Unset → exclude by role (trash+spam); set → that literal list is the whole exclusion. Replace is what preserves doc-6's TASK-15 resolution: opting into archiving trash has to stay possible. The role default is what repairs existing installs, since none of them set the option.

Implementation:
- `ownmail/roles.py` — closed set `inbox/sent/drafts/trash/spam/archive/all`. IMAP resolution order: RFC 6154 SPECIAL-USE flags → case-insensitive `INBOX` (RFC 3501) → bounded leaf-name table. Gmail API: direct system-label-ID map.
- `imap.py` — SPECIAL-USE flags were already parsed out of the LIST response and discarded; now they drive exclusion and All Mail detection. `_get_all_mail_folder`'s four hardcoded localized names deleted in favour of role `all`, so Gmail works in every locale. LIST parsing extracted to `parse_list_response` so setup can reuse it.
- `gmail.py` — the `TRASH`/`SPAM` labelIds re-check now goes through the shared vocabulary. Behaviour unchanged; existing test still covers it.
- `cli.py` — `_setup_imap` runs a LIST over the connection it already opens to test credentials and writes a **commented-out** `exclude_folders:` block naming that server's real trash/spam folders. Commented because uncommenting is an opt-in downgrade to name matching. Discovery is best-effort and never fails setup.
- `commands.py` — `cmd_verify` phase 3 reports archived emails carrying a trash/spam-role label, grouped by label and account, skipping ones already in local trash.
- Docs: `config.example.yaml` gains a full IMAP source example with `exclude_folders` explained; README's old example (which listed Trash/Spam by hand) was showing users how to reproduce the automatic behaviour, now corrected.

AC #2 (canonical labels shown in the sidebar/UI) moved to TASK-5.1 as its AC #3 — the mapping function it needs is delivered here, but there is no label sidebar yet to display it in, and building one is TASK-5.1's whole subject. Not ticked here rather than ticked unverified.

Filed TASK-16 while in `parse_list_response`: a LIST line with a NIL hierarchy delimiter (legal per RFC 3501 for flat namespaces) fails the regex and the folder is dropped silently. Pre-existing, out of scope, current behaviour pinned by a test.

Unblocks TASK-14 — the filter vocabulary it needs now exists. TASK-14 owns exposing role terms in config and unifying gmail.py's hardcoded `-in:trash -in:spam` into that configured path; deliberately not built here.
<!-- SECTION:NOTES:END -->
