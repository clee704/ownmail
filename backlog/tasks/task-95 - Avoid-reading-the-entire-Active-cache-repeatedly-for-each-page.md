---
id: TASK-95
title: Avoid reading the entire Active cache repeatedly for each page
status: To Do
assignee: []
created_date: '2026-09-15 03:27'
updated_date: '2026-09-26 02:24'
labels: []
dependencies: []
references:
  - ownmail/active_cache.py
  - ownmail/active_search.py
  - ownmail/web.py
priority: medium
type: bug
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The TASK-28 Active cache implementation repeatedly calls list_entries from active_count, archive_links, and active_infos during page rendering. Every traversal reads and hashes every cached payload. With eight synthetic 64 KiB messages, one search request made 80 payload reads totaling 5 MiB (10 times the cache volume); a single-message reader made 65 reads totaling 4.06 MiB (8.125 times). Both returned HTTP 200. Counts instrument ActiveCache._read_file and exclude direct parser reads; physical disk traffic was not measured. Make page reads scale with the visible results while preserving cache integrity, current-state metadata, and verified owned/live consolidation. This discovered performance work is outside the fixed five-member Mail ownership scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A synthetic integration regression bounds payload reads for a search page and a single-message reader independently of unrelated cached message bodies.
- [ ] #2 Cached corruption, missing payloads, stale metadata, and ambiguous archive links remain handled without hiding valid owned results.
- [ ] #3 Ownership filters, counts, freshness, pagination, and local-label isolation retain their existing behavior.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: the full-cache traversal pattern is unchanged at HEAD (list_entries reads every payload; active_count, archive_links, active_infos and search each traverse). The read counts above were not re-measured.
<!-- SECTION:NOTES:END -->
