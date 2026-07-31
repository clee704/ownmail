---
id: TASK-17
title: Gmail incremental sync loses messages that arrive mid-run
status: Done
assignee: []
created_date: '2026-07-25 05:52'
updated_date: '2026-07-31 23:19'
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

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The incremental-sync watermark is taken from the users.history.list response's historyId, never from a follow-up getProfile
- [x] #2 Under pagination, the watermark comes from the last history page
- [x] #3 A history response carrying no historyId leaves the watermark unchanged, so the window is re-listed rather than skipped
- [x] #4 A test fakes a history response whose historyId differs from getProfile's and asserts the returned state comes from the history response
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed in `providers/gmail.py`: `_get_messages_since_history` now returns `(new_ids, watermark)` and `get_new_message_ids` passes that tuple straight through. The `get_current_sync_state()` call between the listing and the store is gone — that gap was the race.

Watermark rule: take `historyId` from each history.list response as it arrives, so the last page wins. When a response omits it, the incoming watermark is kept. That re-lists the same window next run (duplicates, deduped downstream) instead of skipping past it — the safe direction to fail, since the whole bug was a watermark advancing past unlisted mail.

`get_current_sync_state()` stays: `archive.py` still calls it on the after-a-full-sync path, where there is no history response to read.

Test change worth flagging: `test_history_sync_returns_new_state` asserted `state == "500"`, the getProfile value — it was pinning the bug in place, so its expectation was wrong and was rewritten. `test_history_paginates` was extended to assert the last page's watermark rather than adding a near-duplicate. Two new cases cover the divergence (history says 400, profile says 500 → 400 wins, getProfile not called) and the missing-historyId fallback. All four were confirmed to fail against a deliberately reintroduced getProfile watermark.
<!-- SECTION:NOTES:END -->
