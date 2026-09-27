---
id: TASK-21
title: 'Multiple label: filters in one query silently return wrong results'
status: Done
assignee: []
created_date: '2026-07-26 03:20'
updated_date: '2026-09-27 08:16'
labels:
  - bug
dependencies: []
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two independent ways to combine label filters both produce a confidently wrong result set instead of an error.

1. 'label:A OR label:B' silently ANDs. query.py emits OR into the FTS5 MATCH string, but label filters become SQL WHERE clauses that database.search joins with AND. The user asks for a union and gets an intersection.

2. 'label:A label:B' silently drops A. database.search keeps a single 'label_filter' local, so the second __LABEL__ marker overwrites the first (same for __RECIPIENT_EMAIL__ / to:). Only the last filter is applied.

Found while building TASK-5.1 (doc-9), which needed a set union over labels and added 'role:' rather than depending on either of these. Not a blocker for that task.

Either make the combination work (collect a list of label filters; AND them via repeated EXISTS, and support OR groups) or reject it with a parse error. Silently answering a different question than the one asked is the part that has to stop. Same defect shape applies to 'to:' with two email addresses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Repeated label:, -label:, to:address and -to:address terms each apply, so results carry every requested label and recipient and none of the excluded ones
- [x] #2 A filter applied as a SQL condition (label:, role:, is:, to:address, from:address, before:, after:, has:) next to OR or inside parentheses returns a parse error naming the filter
- [x] #3 A filter outside parentheses and not next to OR still applies to the whole search, including the ' is:active' pass in active_search
- [x] #4 The search help page states that filters apply to the whole search and cannot be used with OR or inside parentheses
- [x] #5 Regression tests cover each case and fail against the previous code
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 9a7c350.
Decision: AND repeated filters; reject SQL-applied filters as OR operands or inside parentheses. FTS5 binds implicit AND tighter than OR, so a filter anywhere inside an OR alternative is misapplied, not only 'label:A OR label:B'. Union support would need a boolean query tree; role: already unions system labels, and nothing records demand for user-label unions.
1. database.search: first positive label:/to: keeps its JOIN (date-sort index); every further positive or negated term adds an EXISTS clause with its param in step. Remove the single-value negated variables.
2. query.parse_query: after translating a FILTER token, if it added nothing to the FTS string, reject it when depth > 0 or a neighbouring token is OR.
3. Document the rule in help.html and the query.py docstring.
4. Tests in test_database.py and test_query.py; pre-push gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision: repeated filters are ANDed; SQL-applied filters used as OR alternatives or inside parentheses are rejected with a parse error.

The defect was wider than 'label:A OR label:B'. FTS5 binds implicit AND tighter than OR, so any SQL filter inside an OR alternative or a parenthesised group was applied to the whole search instead: '(report label:A) OR x' returned only label:A mail, and 'report OR label:A' left a dangling OR that failed as FTS syntax and returned nothing. Unions were not built: they need a boolean query tree over FTS and SQL terms, role: already unions system labels, and nothing records demand for user-label unions.

A filter elsewhere applies to the whole search, which the help page and query.py docstring now state. That keeps 'invoice OR receipt is:active', which active_search composes, and '(a OR b) label:X' working. 'invoice OR receipt label:X' is accepted as (invoice OR receipt) AND label:X under that rule.

database.search: the first positive label:/to:address term keeps its JOIN for the date-sort index; every further or negated term appends its own EXISTS with its param in step. The single-value negated variables are gone.

query.parse_query: a FILTER token that adds nothing to the FTS string is rejected when depth > 0 or a neighbouring token is OR. The error names the term.

Verification: 16 new cases (TestRepeatedFilters, test_filter_with_or_or_parentheses_is_rejected) fail on 9a7c350 and pass now. Accepted-query cases fail when the OR check is widened to the whole query. Flask test client shows the error on /search and the new text on /help. Pre-push gate passes.
<!-- SECTION:NOTES:END -->
