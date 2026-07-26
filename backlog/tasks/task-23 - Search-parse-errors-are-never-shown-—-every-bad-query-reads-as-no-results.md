---
id: TASK-23
title: Search parse errors are never shown — every bad query reads as 'no results'
status: Done
assignee: []
created_date: '2026-07-26 03:25'
updated_date: '2026-07-26 03:30'
labels:
  - bug
dependencies: []
priority: high
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
query.py produces careful error messages ('Unclosed quote after ...', "Invalid date format for 'before:'", "ownmail does not archive read/unread state, so 'label:UNREAD' is not searchable"). None of them reach a user.

database.search checks parsed.has_error(), prints the message to stdout, and returns []. Its own comment says 'The caller (web.py or cli) should display parsed.error to the user' — no caller does. web.py's search route only sets search_error from an exception, and parse errors are not exceptions, so search.html renders 'No results found for ...' instead.

Consequences: a typo'd filter or unbalanced quote looks like an empty archive; TASK-5.3's deliberately-worded label:UNREAD message is dead code; the same is true of every validation message in the parser.

Fix shape: web.py's search route validates with query.parse_query before calling archive.search and renders parsed.error through the existing search_error path. Parsing is a tokenizer over a short string, so the double parse costs nothing and no signature changes are needed. Check the CLI search path too.

Found while building TASK-5.1 (doc-9), whose new role: term needs its 'Unknown role' message to be visible.
<!-- SECTION:DESCRIPTION:END -->
