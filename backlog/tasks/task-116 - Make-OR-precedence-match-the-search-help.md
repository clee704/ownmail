---
id: TASK-116
title: Make OR precedence match the search help
status: To Do
assignee: []
created_date: '2026-09-27 08:16'
labels:
  - search
  - bug
dependencies: []
priority: medium
ordinal: 10500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
FTS5 binds implicit AND tighter than OR, so 'attachment:pdf report OR invoice' means (PDF attachment AND report) OR invoice. The help page's Examples table says it finds PDFs with report or invoice. Checked against FTS5: the query also returns invoice mail with no attachment.

Gmail, whose syntax ownmail follows, binds OR tighter than AND. Either correct the example to 'attachment:pdf (report OR invoice)' and state the precedence on the help page, or have the parser group each OR chain so 'a b OR c' means a AND (b OR c). The second changes results for existing queries.

Text terms only: since TASK-21, SQL-applied filters apply to the whole search and cannot be OR alternatives. Found while fixing TASK-21.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The help page describes OR precedence as search applies it, and every Boolean and Example row returns what its description says
- [ ] #2 A test runs the documented OR example through search() and asserts its result
<!-- AC:END -->
