---
id: TASK-5.3
title: Standardize read/unread state across providers
status: Done
assignee: []
created_date: '2026-07-24 04:56'
updated_date: '2026-07-25 06:20'
labels: []
milestone: m-1
dependencies: []
parent_task_id: TASK-5
priority: high
ordinal: 4
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Read/unread was represented inconsistently: Gmail's REST API exposes it as a pseudo-label 'UNREAD' that landed in the labels array alongside real labels (and rendered as a label chip in the web detail view), while imap.py never fetched the \Seen flag at all. The 'seen'/'_seen_map' names in imap.py are unrelated folder-dedup bookkeeping.

Resolved by removing the asymmetry downward rather than upward - ownmail does not archive read/unread state at all. See Implementation Notes for why capturing it was rejected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Read/unread is not archived by either provider: Gmail's UNREAD is dropped at label resolution, IMAP adds no \Seen capture
- [x] #2 Existing archives converge on the same state - rebuild --only sidecars purges UNREAD from sidecars and email_labels
- [x] #3 label:UNREAD reports why it is unsearchable instead of silently returning no results
- [x] #4 A differently cased IMAP folder ('Unread') is treated as real archive content and kept
<!-- AC:END -->



## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Decision: don't archive read/unread at all

The task assumed the fix was to add \Seen capture to IMAP and normalize both
providers onto a shared field (probably an is_unread column). Rejected after
checking whether a captured value could be kept true.

**It can't.** Sync filters out already-downloaded messages (archive.py:247), so
read state is frozen at download time. Download is arrival-driven: ownmail picks
mail up hours after it lands, before it's been worked through. The only refresh
path is `update-labels` (commands.py:1362) - one messages.get per message across
the whole archive, run manually. So a stored value skews to 'unread' at capture
and never corrects; the longer an archive runs, the more confidently it claims
thousands of unread messages that were read years ago.

Weighed against use: searching an archive doesn't need read state; 'what did I
never get to?' only matters for recent mail, which is exactly where the value is
wrong; and mbox export (TASK-9) would hand another client 15k bold messages,
worse than marking all read. The initial backfill is the one honest snapshot,
and it gets drowned by everything captured after it.

## What shipped

- `roles.EPHEMERAL_LABELS` - the set, with the reasoning at the definition.
  Matched **exactly**, never case-folded: Gmail system label IDs are always
  upper-case and can't collide with a user label, while an IMAP folder named
  `Unread` is real archive content.
- `gmail.py` `_resolve_label_names` - the single choke point both the batch and
  per-message download paths run through, so one filter covers both.
- `rebuild --only sidecars` - purges UNREAD from existing sidecars and
  email_labels, counted separately in the summary. Backfill path strips it too,
  so a sidecar written from stale DB labels can't resurrect it.
- `query.py` - `label:UNREAD` returns a parse error. Deliberately polarity-neutral
  wording ('is not searchable'), because `-label:UNREAD` would match everything,
  not nothing.

No schema change, no SIDECAR_VERSION bump - so no STOP sign-off was needed.

## Caveats

- Case-exact matching means `label:unread` (lower-case) gets no explanatory
  error, just zero results. Accepted: erroring on it would make a legitimately
  named IMAP folder unsearchable with no escape hatch, and that failure has no
  workaround while this one is merely less helpful.
- Gmail still leaks other non-topical pseudo-labels (STARRED, IMPORTANT,
  CATEGORY_*) into the labels array. Same class of question, different answers
  per label - STARRED is durable user intent, IMPORTANT is an ML guess that
  drifts. Filed as TASK-19 rather than absorbed here.
<!-- SECTION:NOTES:END -->
