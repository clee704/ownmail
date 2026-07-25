---
id: TASK-14.3
title: Make capture eligibility-driven rather than arrival-driven
status: To Do
assignee: []
created_date: '2026-07-25 05:53'
labels: []
milestone: m-5
dependencies:
  - TASK-17
parent_task_id: TASK-14
priority: high
ordinal: 3
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prerequisite for TASK-14.1, split out of it once the hole audit showed the config surface was the small half.

THE PROBLEM. A download filter is a statement about a message's CURRENT state on the server. Every mechanism underneath it is a statement about ARRIVAL:
- Gmail API asks for historyTypes=['messageAdded'] only (gmail.py:214)
- IMAP tracks a max-UID watermark per folder
- Gmail-over-IMAP watermarks All Mail, where a message's UID never changes after arrival

So a message that is ineligible when it arrives and becomes eligible later is never revisited. Concretely, all of these are missed on the Gmail API path:
- inbox -> archive (user files a message)
- trash -> archive (user restores a message they had deleted)
- spam -> inbox -> archive

None of this bites today, for one reason only: the inbox is downloaded, so essentially everything is captured eagerly on arrival before it can transition anywhere. That eager capture is the safety net a download filter removes. This must land before any filter ships, or the filter turns a working archive into one with silent holes.

SHAPE OF THE FIX (decide before building):
- Treat a sync signal as producing a CANDIDATE message id, not a download decision. Then re-evaluate each candidate's current state against the filter. A message trashed and restored between two runs produces two events and one correct answer.
- Gmail API: subscribe to labelAdded/labelRemoved alongside messageAdded. Every transition then produces a candidate.
- Gmail-over-IMAP: departure from a folder leaves no trace (imap.py:546-551 only sees UIDs above the watermark), so folders whose membership the filter depends on must be rescanned in full each run. Bounded and cheap for INBOX; confirm before assuming for others.
- Plain IMAP: already correct. A folder move allocates a new UID above the destination's watermark, so transitions are detected for free. No change needed.
- REJECTED: recording filtered-but-seen ids as 'deferred' and re-checking them. Grows without bound — every message ever trashed would be re-checked forever.

Also in scope, because they are the same class of problem (hole numbers refer to the audit in TASK-14.1's notes):
- Hole 1: widening the filter must force a full resync. Previously-skipped messages sit below the watermark, so relaxing the filter otherwise captures nothing retroactively, silently. Detect the filter change and invalidate the watermark.
- Hole 6: keep 'do not download from here' separate from 'do not read labels from here'. _list_folders currently drops excluded folders entirely, which also removes them as label sources (_scan_gmail uses non-All-Mail folders purely for label mapping).

Depends on TASK-17: the history watermark race makes incremental sync lossy, and this task makes incremental sync the only capture path. Fixing the race first keeps the two failure modes separable.
<!-- SECTION:DESCRIPTION:END -->
