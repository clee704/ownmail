---
id: TASK-14.1
title: Configurable download filter in canonical role terms
status: To Do
assignee: []
created_date: '2026-07-25 05:38'
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
