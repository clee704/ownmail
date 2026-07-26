---
id: TASK-27
title: >-
  Label strings are not round-tripped safely — comma-joined storage, and a
  malformed value in the wild
status: To Do
assignee: []
created_date: '2026-07-26 05:31'
labels:
  - bug
dependencies: []
priority: medium
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two related findings about how label strings survive the trip into the archive.

1. COMMA-JOINED STORAGE CANNOT ROUND-TRIP A LABEL CONTAINING A COMMA. database.py:853-864 stores labels as one comma-separated string and re-splits it on ',' to populate email_labels. Gmail user labels may contain commas, and so may IMAP folder names. A label 'Receipts, 2026' silently becomes two labels, 'Receipts' and '2026', in the index and in the sidebar. There is no escaping and no way to tell a split label from two real ones after the fact.

2. A MALFORMED LABEL REACHED A REAL ARCHIVE. Observed in a real archive; synthetic example:

   SENT <id1@mail.gmail.com> <id2@mail.gmail.com> <id3@mail.gmail.com>

That is a role token followed by what is unmistakably a References or In-Reply-To header value. It contains no comma, so the split above passed it through intact as a single label. It renders in the sidebar as a user label, because neither the Gmail ID map nor the leaf-name table matches the whole string.

Something concatenated a label with header content. Worth tracing before deciding the fix — candidates include a folded or multi-line IMAP FETCH response parsed as one line, a literal-length miscount, or the import path (TASK-7). Do not guess. An archive holding the malformed label also holds the messages that produced it, so identify the actual producer from those before changing anything.

The two findings share a shape — nothing validates a label string between the provider and the index. Sanity bounds worth considering once the producer is known: reject or flag a label containing '<' and '@' together, or one implausibly long.

Fixing (1) touches how labels are persisted, so check whether it needs a schema change before starting — that would make it a STOP item.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The producer of the malformed value is identified from the affected messages, not inferred
- [ ] #2 A label containing a comma survives capture, indexing and search as one label, or the limitation is documented and enforced with an explicit rejection
- [ ] #3 Existing archives holding a malformed label have a stated disposition — repaired, reported, or left alone with the reason recorded
<!-- AC:END -->
