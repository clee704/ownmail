---
id: TASK-95
title: Avoid reading the entire Active cache repeatedly for each page
status: Done
assignee:
  - '@codex'
created_date: '2026-09-15 03:27'
updated_date: '2026-10-20 04:58'
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
- [x] #1 A synthetic integration regression bounds payload reads for a search page and a single-message reader independently of unrelated cached message bodies.
- [x] #2 Cached corruption, missing payloads, stale metadata, and ambiguous archive links remain handled without hiding valid owned results.
- [x] #3 Ownership filters, counts, freshness, pagination, and local-label isolation retain their existing behavior.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 055a7fc0397a5934d2b0a90d797fce496083b708. Direct commits to master under the maintainer workflow.
1. Measure synthetic search and reader payload reads, and identify existing cache validation and consolidation helpers.
2. Remove repeated full-payload traversals from page counts, links and freshness while retaining file integrity checks and current metadata. Keep database schemas and provider behavior unchanged.
3. Add bounded-read integration regressions and preserve corruption, missing-file, stale-metadata, ambiguous-link, filter, pagination and label-isolation behavior. Prove new regression assertions fail without the fix.
4. Review the complete task diff, run focused checks and the full pre-push gate with browser tests required, commit the implementation, then close the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: the full-cache traversal pattern is unchanged at HEAD (list_entries reads every payload; active_count, archive_links, active_infos and search each traverse). The read counts above were not re-measured.

2026-10-19 scope: finish TASK-95 only. Cache storage redesign, provider sync changes, real archive operations, schema changes, dependencies and publishing are out of scope. Initial working tree is clean. Existing list_entries validates every payload on each traversal; active_count, archive_links and active_infos all use that path. Next action: reproduce read amplification with synthetic fixtures and implement a bounded validation reuse strategy.

2026-10-19 implementation and focused verification:
- ActiveCache reuses successful payload verification keyed by filename, device, inode, size, mtime_ns and ctime_ns. Every call still checks file safety and reads current entry/source metadata; read() hashes the bytes it returns. No message bodies are retained in memory. Newly written payloads are verified on disk before reuse.
- Synthetic HTTP regressions use one visible target and zero/eight unrelated 64 KiB cached messages. Before the fix, search made 10/82 payload reads and reader made 9/73; after the fix both made zero verification payload reads. These counts instrument _read_file and exclude direct parser reads; no physical disk-traffic claim. All four regression cases failed against the original implementation.
- Mutation coverage includes same-size edits with restored mtime, inode replacement, missing files, symlinks, hardlinks and changes during verification. Extended corrupt/missing live and dual-state cases retain valid owned results and correct counts. Existing freshness, ambiguous-link, ownership-filter, pagination and local-label isolation checks pass.
- Focused Active cache/search/scope/web/live-sync suite: 224 passed. Ruff check, format check and diff whitespace check pass. Full-task diff reviewed against 055a7fc; full pre-push gate remains pending.
- Cold startup/rebuild still verifies and indexes all cached payloads. Metadata traversal and verification of owned candidate files remain unchanged; further optimization is out of scope.

Full gate found a required compatibility fix: the read-only CLI _SearchCache initializes without ActiveCache.__init__, so it needs its own empty verification map before inherited list_entries/path calls. Gate result: 5109 passed, 10 failed from the missing state, 96.53% coverage. Correct this constructor and include read-only search/read JSON tests before rerunning the full gate. Earlier no-outstanding-findings review is superseded by this gate result.

Compatibility correction: initialize the verification map in the read-only cache constructor before inherited validation. Existing tests cover the failure, so no duplicate regression was added. Expanded focused suite including all Active checks, read-only search, read JSON and search JSON passes: 330 tests with browser tests required. Ruff and diff checks pass. Independent full-task review and final gate rerun are in progress.
Primary break-to-fail checks rejected three in-memory mutations: omitting ctime from the signature, skipping read() hash validation, and trusting the file signature after a concurrent edit. The restored implementation passes all seven affected cases; no source files were changed for these mutations.

Independent review of the full task diff, including the read-only constructor correction, found no actionable introduced findings. It checked signature/hash coupling, file safety, invalidation, concurrent changes, metadata freshness, put/remove/rebuild behavior, owned/live consolidation and fresh-byte hashing in JSON reads. Final full gate remains the only pending closure check.

Final code verification: full required-browser suite passed all 5119 tests with 96.70% branch-inclusive coverage. Pre-commit reported files modified because the task notes were updated during that run; no source or test change occurred. Commit this tested implementation checkpoint, then repeat the exact pre-push gate with all tracked files stable before closure.

Final closure: implementation committed as 40440cf. With tracked files stable, OWNMAIL_REQUIRE_BROWSER_TESTS=1 pre-commit run -a --hook-stage pre-push passed every hook, including the full suite and 96.70% branch-inclusive coverage. All acceptance criteria are verified, independent review has no outstanding findings, and no runtime, schema, provider or real archive changes were required. Closure changes only this task record.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reuse verified Active payload file signatures while checking current metadata and hashing every explicit content read. Synthetic search/reader requests make no unrelated payload reads; corruption, missing/unsafe files, ownership, counts, pagination and freshness remain covered. Include the read-only CLI cache constructor. Expanded focused suite: 330 passed; complete suite: 5119 passed; required-browser pre-push gate passed with 96.70% coverage. Independent review found no remaining issue. Implementation: 40440cf. Cold startup/rebuild retains full payload verification.
<!-- SECTION:FINAL_SUMMARY:END -->
