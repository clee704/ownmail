---
id: TASK-22
title: FTS + label + date in one query binds parameters in the wrong order
status: To Do
assignee: []
created_date: '2026-07-26 03:23'
labels:
  - bug
dependencies: []
priority: high
ordinal: 28000
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
