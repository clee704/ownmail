---
id: TASK-5.2
title: >-
  Standardize system labels/folders (Trash, Spam, Inbox, Sent...) across
  providers
status: To Do
assignee: []
created_date: '2026-07-24 04:54'
updated_date: '2026-07-24 23:01'
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
- [ ] #1 Design doc/decision recorded on canonical system-label mapping (or an explicit decision not to do it)
- [ ] #2 If adopted: known provider folder names map to canonical labels shown in sidebar/UI without losing the raw label for search
- [ ] #3 IMAP SPECIAL-USE (\Trash, \Junk, etc.) is used to detect system folders when the server advertises it
- [ ] #4 Fallback default exclude list covers common non-Gmail trash/spam folder names, not just [Gmail]/Trash and [Gmail]/Spam
- [ ] #5 exclude_folders documented in config.example.yaml
- [ ] #6 Existing archived emails wrongly carrying a synced Trash/Spam-equivalent label are identified (verify --fix candidate?) so already-polluted archives can be cleaned up, not just future syncs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed, not just theoretical: imap.py:28 DEFAULT_EXCLUDE_FOLDERS = ["[Gmail]/Trash", "[Gmail]/Spam"] is a literal Gmail-only folder-name match. Any IMAP account whose trash folder is named anything else (plain "Trash", "Deleted Items", "INBOX.Trash", etc.) skips the exclusion entirely and gets archived as a normally-labeled email - reported by the user finding a real archived email with label "Trash". No IMAP SPECIAL-USE (RFC 6154) support exists in imap.py either, which is the actual provider-agnostic way to detect \Trash/\Junk/\Sent/\Drafts/\Archive regardless of naming. Fix should probably: (1) use SPECIAL-USE flags from the LIST response when the server advertises them, falling back to (2) a broader default literal-name list covering common providers (plain 'Trash', 'Deleted Items', 'Junk', 'Spam', ...) - and surface exclude_folders in config.example.yaml, which currently doesn't document the option at all even though the per-source parameter already exists in code.

**2026-07-24 — this task now gates TASK-14 (purge).** Originally scoped as a UI/display concern: canonical system labels so a multi-account sidebar doesn't show fragmented per-provider folders.

TASK-14's download filter is configured in terms of system labels (exclude trash, spam, drafts, inbox), and providers spell those differently — `TRASH` vs `Trash` vs `[Gmail]/Trash` vs `Deleted Items`, plus IMAP SPECIAL-USE flags. So the canonical mapping is a correctness precondition for purge, not just presentation: if `inbox` fails to resolve on some provider, inbox messages pass the filter, get downloaded, and get purged from the server — exactly the outcome TASK-14's design exists to prevent.

AC #3 (SPECIAL-USE detection) and AC #5 (`exclude_folders` in config.example.yaml) are the parts TASK-14 leans on most directly.

Sharpened: the mapping must be **semantic (a per-message role)**, not a folder-name lookup table. Evidence that names don't work — IMAP INBOX is a folder while Gmail INBOX is a label with different membership semantics; IMAP names are case-insensitive per RFC 3501; Gmail-over-IMAP has a message in both INBOX and [Gmail]/All Mail simultaneously; and folder names are localized (imap.py:211-219 hardcodes four language variants of All Mail and misses many more). AC #3's SPECIAL-USE detection is the right primitive for this, with a role fallback where the server doesn't advertise it.
<!-- SECTION:NOTES:END -->
