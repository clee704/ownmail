---
id: TASK-17
title: Gmail incremental sync loses messages that arrive mid-run
status: To Do
assignee: []
created_date: '2026-07-25 05:52'
labels: []
milestone: m-5
dependencies: []
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
gmail.py:191-192 takes the new sync watermark from a SEPARATE API call than the one that listed the messages:

    new_ids = self._get_messages_since_history(since_state)
    new_state = self.get_current_sync_state()   # users.getProfile -> historyId

A message that arrives between the history.list pagination finishing and the getProfile call has a historyId below the stored watermark but was never returned by the listing. The next run starts from the newer watermark, so the message is never seen again. Permanent, silent loss — no error, no retry.

The window is small but it is hit on every single incremental run, and the busier the mailbox the likelier it lands in it. It also survives the error_count==0 gate in archive.py:468, because there is no error: the message simply was never listed.

FIX: users.history.list responses carry their own 'historyId' field — the mailbox's current history record as of that response. That is the correct watermark and it is currently discarded (_get_messages_since_history reads only 'history' and 'nextPageToken'). Take the watermark from the last history page instead of a follow-up getProfile. get_current_sync_state() is still needed for the after-a-full-sync path, so it stays.

WHY NOW: independently a real data-loss bug, but it also becomes load-bearing under TASK-14.1. Today the inbox is downloaded eagerly, so nearly everything is captured on arrival and this race only matters for the narrow case where the missed message is never re-listed. Once a download filter makes incremental sync the primary capture path, every miss is permanent.

Verify with a test that fakes a history response whose historyId differs from getProfile's, and asserts the stored state comes from the history response.
<!-- SECTION:DESCRIPTION:END -->
