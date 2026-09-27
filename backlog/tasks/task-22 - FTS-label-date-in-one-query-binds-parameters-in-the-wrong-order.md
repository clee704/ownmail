---
id: TASK-22
title: FTS + label + date in one query binds parameters in the wrong order
status: Done
assignee: []
created_date: '2026-07-26 03:23'
updated_date: '2026-09-27 08:02'
labels:
  - bug
dependencies: []
priority: high
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
database.search's FTS path binds extra_params before params, but emits their SQL clauses in the opposite order. Any query that combines a text term, a label:/to:email filter, AND a placeholder-bearing clause (before:, after:, account) silently returns wrong results.

Reproduced against a one-email archive (subject 'Quarterly report', label INBOX, dated 2024-03-01):

    label:INBOX                                -> 1 row  (correct)
    quarterly                                  -> 1 row  (correct)
    quarterly label:INBOX                      -> 1 row  (correct)
    quarterly before:2024-06-01                -> 1 row  (correct)
    quarterly label:INBOX before:2024-06-01    -> 0 rows (WRONG)
    label:INBOX before:2024-06-01              -> 1 row  (correct)

Both code paths are affected, by the same root cause — SQL clause order and bound-parameter order are maintained independently and disagree.

**FTS path.** where_sql is ' AND '.join([where_sql] + extra_where), so the original where_clauses placeholders come first in the SQL text, but fts_params is built as [fts_query] + extra_params + params. 'INBOX' gets bound to 'e.email_date < ?' and the date to 'el.label = ?'.

**Non-FTS path.** Two inserted filters swap. Both recipient and label do where_clauses.insert(0, ...) while appending to filter_params, so the second insert lands in front of the first and the two params are transposed. Same archive:

    to:me@example.com                          -> 1 row  (correct)
    label:INBOX                                -> 1 row  (correct)
    to:me@example.com label:INBOX              -> 0 rows (WRONG)
    label:INBOX to:me@example.com              -> 0 rows (WRONG)

The FTS side is likely a one-line reorder to [fts_query] + params + extra_params. The non-FTS side needs the inserts to stop fighting each other (build the filter clauses as a list and prepend once, or append and keep params in step). Both need regression tests per combination — fts+label+date, fts+to+date, fts+label+account, to+label — since the existing test only asserts 'parsed is not None' and never runs a search.

The real fix is probably to stop tracking clauses and params in separate lists in this function; every instance of this bug comes from that split.

Found while building TASK-5.1. The new role: filter appends its clause to where_clauses and its params to params, so those two stay in step and role: alone is unaffected; 'text role:inbox label:X' still hits the FTS defect.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Text + label: + before:/after: returns the matching messages
- [x] #2 Text + to:address + before:/after: returns the matching messages
- [x] #3 Text + label: with the account argument returns the matching messages
- [x] #4 to:address + label: without text returns the matching messages in either term order
- [x] #5 Regression tests run each combination through search() and fail against the old binding order
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 96cab63.
1. Add search() regression tests for each combination listed in the description; confirm they fail.
2. Build positive label/recipient JOINs, clauses and params in the shared section, appending clause and param together, so both paths bind in SQL order. Drop the path-specific extra_where/extra_params and filter_params lists.
3. Keep the el.email_date sort rewrite for label-filtered date sorts.
4. Run the pre-push gate.
Out of scope: multiple label:/to: terms and OR groups (TASK-21).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Positive label: and to:address filters now add their JOIN, clause and param in the shared section, next to every other filter, so both search paths bind values in SQL order. The path-specific extra_where/extra_params (FTS) and filter_params with insert(0) (table-only) are gone, and the label-aware el.email_date sort column is chosen once.

The account argument was also affected: 'text label:X' with account bound the label to e.account. The new tests cover it.

Clauses and params are still separate lists, but every producer in search() now appends to both together. TASK-21 can turn label_filter/recipient_email_filter into lists on the same pattern.

EXPLAIN QUERY PLAN for label-only, to+label and text+label queries is unchanged by the fix.

Verification: TestSearchFilterCombinations (7 cases, each with decoys that fail exactly one filter) fails in all 7 cases on 96cab63 and passes after the fix; pre-push gate passes.
<!-- SECTION:NOTES:END -->
