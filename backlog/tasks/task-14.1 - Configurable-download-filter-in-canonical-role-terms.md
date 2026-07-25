---
id: TASK-14.1
title: Configurable download filter in canonical role terms
status: To Do
assignee: []
created_date: '2026-07-25 05:38'
updated_date: '2026-07-25 05:44'
labels: []
milestone: m-5
dependencies: []
parent_task_id: TASK-14
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Knob 2 of doc-6, split out of TASK-14 because it is NOT a STOP item: it changes only what gets downloaded, deleting nothing and needing no OAuth scope change. Unblocked now that TASK-5.2 landed.

Exposes a per-source download filter written in canonical role terms (roles.py from TASK-5.2), and unifies the three inconsistent filter sites: imap.py exclude_folders, gmail.py's hardcoded '-in:trash -in:spam', and gmail.py's TRASH/SPAM labelIds re-check.

WHY EXCLUDING INBOX MATTERS INDEPENDENTLY OF PURGE (user, 2026-07-25): doc-6 justifies the inbox exclusion only via purge safety. There is a second, independent reason that holds with purge off. In the two-path model, the mail client owns triage; inbox means 'not yet decided'. If ownmail archives inbox mail, a message the user later deletes in the client is already captured, so the delete decision has to be made a second time in ownmail. Adverts, one-time codes and similar arrive in the inbox, get deleted in the client, and would otherwise persist in the archive forever.

BLOCKER TO SOLVE FIRST - incremental sync cannot see 'filtered out earlier, eligible now'. Both Gmail paths break; plain IMAP does not:
- Gmail API: get_new_message_ids passes historyTypes=['messageAdded'] (gmail.py:214). A message skipped on arrival because it was in INBOX, then archived by the user, emits labelRemoved - never messageAdded. Incremental sync never revisits it, so it is missed permanently until a full sync.
- Gmail-over-IMAP: All Mail is the sole download source (imap.py) and the message is in All Mail from arrival with a fixed UID. The watermark is max UID in All Mail; archiving does not change the UID, so the incremental scan never revisits it. Same gap.
- Plain IMAP (mailbox.org): a move from INBOX to Archive allocates a NEW UID in the destination folder, above that folder's watermark, so it is picked up normally. No gap.

Candidate fixes: add labelAdded/labelRemoved to historyTypes for Gmail; or record filtered-but-seen message IDs as deferred and re-check them each run. Second option is provider-agnostic and covers both Gmail paths, at the cost of persisted state. Decide before building.

Note this is exactly doc-6's 'filter is evaluated live against server state' requirement, which was written for purge-time sweep. It applies to download too, and the current incremental machinery cannot express it.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**2026-07-25 — the gap is broader than the inbox rule, and today's design is only accidentally safe.**

User's scenario: trash a message in the mail client, ownmail runs (trash excluded, not downloaded), then move it out of Trash into Archive because it turned out to be worth keeping. Is it captured?

- **Gmail API: no, missed.** Trashing is `labelAdded TRASH`, restoring is `labelRemoved TRASH`. Neither is `messageAdded`, which is the only history type requested (gmail.py:214). The message is never revisited.
- **Plain IMAP (mailbox.org): yes, captured.** The Trash→Archive move allocates a new UID in Archive above that folder's watermark. No duplicate results either — archive.py:373 content-hash checks before writing.
- **Gmail-over-IMAP: captured**, unlike the inbox case. Gmail's IMAP mapping makes All Mail and Trash mutually exclusive, so restoring re-appends to All Mail with a fresh UID above the watermark.

**Why this generalizes.** This is not a second bug next to the inbox one, it is the same root cause with a wider blast radius. Any download filter turns capture into a question of detecting *transitions into eligibility*, and the current incremental machinery only detects *arrival*. On the Gmail API path every transition is invisible: inbox→archive, trash→archive, spam→inbox→archive.

**Why it doesn't bite today.** Trash has always been excluded, so this hole nominally exists now. It is harmless only because inbox *is* downloaded — every message is captured eagerly on arrival, before it can ever reach trash. Excluding inbox removes that safety net and promotes transition-detection from a corner case to the primary capture path. So the inbox filter cannot ship before this is solved.

**Preferred fix (decide before building).** Reject the "record filtered-but-seen IDs as deferred" option as the primary mechanism: it grows without bound, since every trashed message would be re-checked forever. Instead:

- Gmail API: request `labelAdded`/`labelRemoved` alongside `messageAdded`, and treat any history event as producing a *candidate* ID rather than a download.
- Then re-evaluate each candidate's **current** state against the filter, rather than replaying the event sequence. A message trashed and restored between two runs yields two events but one correct answer. This is doc-6's "filter is evaluated live against server state", which was written for purge-time sweep and turns out to be equally required at download time.
- Both IMAP paths already satisfy this via UID reallocation and need no change.
<!-- SECTION:NOTES:END -->
