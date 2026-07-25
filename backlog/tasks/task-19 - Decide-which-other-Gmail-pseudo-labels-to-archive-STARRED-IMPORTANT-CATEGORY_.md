---
id: TASK-19
title: >-
  Configurable label exclusion for platform auto-labels (IMPORTANT, CATEGORY_*,
  STARRED)
status: To Do
assignee: []
created_date: '2026-07-25 06:20'
updated_date: '2026-07-25 06:38'
labels: []
dependencies: []
priority: medium
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-5.3 dropped Gmail's UNREAD unconditionally: nothing refreshes a captured value, so an archived 'unread' becomes false over time. Gmail's other non-topical pseudo-labels (IMPORTANT, CATEGORY_*, STARRED, CHAT) still pass through _resolve_label_names into the labels array, but they are a different kind of question — taste, not correctness. So this task ships a config knob rather than a maintainer ruling on each label.

## The line between the tiers

Does a stored value become **false**, or merely **unwanted**?

- UNREAD becomes false. Stays hardcoded in roles.EPHEMERAL_LABELS, dropped at capture, deliberately NOT configurable — a knob there only lets a user opt into a lie.
- IMPORTANT stays true as a statement about the past ('Gmail flagged this at delivery') even when it is noise to the reader.
- CATEGORY_PERSONAL/SOCIAL/PROMOTIONS/UPDATES/FORUMS — Gmail's tab classification. Stable, topical, weakest case for dropping.
- CHAT — closer to a message type than a label.

Everything in the second tier is captured and then filtered.

## Design: filter the index, not the archive

Do NOT drop excluded labels at capture. Instead:

- The sidecar stores every label the provider sent (minus UNREAD). It is the record of what the server said at capture time.
- exclude_labels is applied when populating the email_labels table — the rebuildable cache. Search and the web UI never see excluded labels.
- rebuild --only sidecars re-applies whatever the config currently says, in both directions. This is the 'bulk edit for already-downloaded messages': the purge path TASK-5.3 built, reading config instead of a hardcoded frozenset.

Why this over blocking at capture:

- **Reversible both ways, permanently.** Flip the config, rebuild, and an excluded label comes back — it never left the archive. Capture-time blocking is one-way.
- **No purge deadline.** update-labels can currently re-fetch dropped labels from the server (commands.py:1362), but TASK-14.2 trashes the server copy once archived, closing that window for good. Filtering the index has no such dependency.
- **Less code.** One filter point instead of two, and no destructive path to test.
- It is what invariant #1 is for: files are truth, the DB is a rebuildable index.

Consequence for _reconcile_label_sidecars: 'DB matches sidecar' becomes 'DB matches filter(sidecar)'. The current equality comparison needs to account for that.

## Open question this does NOT resolve

STARRED is a deliberate user act and the strongest candidate for archiving. It is also not an asymmetry of concept, only of spelling: Gmail's STARRED label and RFC 3501's \Flagged are the same stored bit, and Gmail's own IMAP interface maps one to the other. Starring in the web UI sets \Flagged over IMAP.

That makes it a roles.py problem, not a new-capability problem — the same shape as TRASH vs [Gmail]/Trash that doc-7 already solved. A canonical `flagged` role resolving from both the Gmail STARRED label and the IMAP \Flagged flag would close it, and doc-7 explicitly parked `flagged` as 'nothing consumes it yet'. This task is that consumer.

Still a real decision, because ownmail does not read IMAP FLAGS at all today. Capturing \Flagged means adding FLAGS to the FETCH in imap.py — which must keep readonly=True / BODY.PEEK, since fetching RFC822 on a writable mailbox sets \Seen as a side effect and would silently mark the user's mailbox read.

Adjacent, out of scope, worth filing if pursued: \Answered has no Gmail API counterpart at all (Gmail infers reply state from threads). It stays true forever, so it passes the false-vs-unwanted test, but capturing it creates the mirror-image asymmetry where IMAP archives carry it and Gmail archives cannot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-source exclude_labels config option, defaulting to empty (archive and index everything the provider sent)
- [ ] #2 Sidecars keep every provider label; exclusion happens only when populating email_labels
- [ ] #3 rebuild --only sidecars re-applies the current exclude_labels in both directions - removing a label from the config restores it to the index without a server round-trip
- [ ] #4 _reconcile_label_sidecars compares DB against filter(sidecar), not raw sidecar equality
- [ ] #5 UNREAD stays dropped at capture via roles.EPHEMERAL_LABELS and is not reachable through exclude_labels
- [ ] #6 STARRED is handled as a canonical `flagged` role resolving from both Gmail STARRED and IMAP \Flagged, or the decision not to is recorded
<!-- AC:END -->
