---
id: TASK-20
title: update-labels destroys multi-folder labels on IMAP sources
status: Done
assignee: []
created_date: '2026-07-25 06:49'
updated_date: '2026-08-06 04:05'
labels: []
dependencies: []
priority: high
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`ownmail update-labels` is destructive on IMAP archives and near-useless on Gmail ones. Both defects live in cmd_update_labels (commands.py).

## IMAP: flattens multi-folder membership (data loss)

_update_labels_imap (commands.py:1300) never connects to the server. It parses the folder out of the stored provider_id ("folder:uid"), then:

    DELETE FROM email_labels WHERE email_rowid = ?
    INSERT ... VALUES (rowid, folder, email_date)
    sidecar.write_labels(path, [folder])

So it replaces every label with a single one — the folder the message was first downloaded from. Any additional folder membership discovered by the dedup scan (_scan_standard / _get_labels_for_downloaded, which exist precisely to find messages appearing in several folders) is destroyed, in the DB *and* in the sidecar. Since the sidecar is the source of truth, rebuild --only sidecars then propagates the flattened state rather than repairing it.

The command's docstring calls this 'Update labels ... No IMAP connection needed', so the behaviour is intentional as written — but it is only correct for a single-folder archive, and it is offered as a repair tool.

## Gmail: cannot clear, and hides transient failures

_update_labels_gmail (commands.py:1362):

    labels = provider.get_labels_for_message(provider_id)
    if not labels:
        skip_count += 1
        continue

A message whose labels were all removed on the server keeps its stale ones locally — the one case a label-refresh tool most needs to handle. And get_labels_for_message returns [] on HttpError (gmail.py:369), so a rate-limit or network failure is indistinguishable from 'no labels' and is silently counted as a skip.

Interacts with TASK-5.3: a Gmail message whose only label was UNREAD now resolves to [], so update-labels skips it. rebuild --only sidecars still cleans it, so no archive is stuck, but update-labels is not the path that fixes it.

## Fix direction

For IMAP, either connect and re-scan folder membership properly, or delete the offline path — a repair tool that loses data is worse than no repair tool. For Gmail, distinguish 'server returned no labels' from 'the call failed': let the error propagate or return None, and only clear on a confirmed empty result.

## Correction — scope, on reading the code (2026-08-05)

Two claims above are wrong, and the fix is narrower than they imply.

**The blast radius is smaller than 'destroys multi-folder labels'.** cmd_update_labels selects only emails with *no* rows in email_labels (`AND NOT EXISTS (SELECT 1 FROM email_labels ...)`), and has since before this task was filed. So the DELETE is a no-op by construction and no DB label is ever replaced. What *is* real: both paths call `sidecar.write_labels` unconditionally, overwriting the file — the source of truth — with a derived value. Reachable whenever DB label rows are missing while sidecars are not, i.e. after losing the DB and running plain `rebuild` without `rebuild --only sidecars`. Narrower, still data loss on the authoritative copy.

**It is a backfill, not a re-snapshot.** The Gmail complaint 'a message whose labels were all removed on the server keeps its stale ones locally' describes something the command cannot do at all: a message with stale labels has label rows, so it is never selected. AC #3 asked for that capability — but doc-8 rules it out, since re-reading label state after capture lets a non-authoritative source overwrite the authoritative one. Dropped rather than implemented, and doc-8's own description of this command (which called it a re-snapshot) corrected to match.

The Gmail HttpError → `[]` defect is real exactly as filed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 update-labels on an IMAP source no longer reduces a multi-folder message to a single label
- [x] #2 update-labels on a Gmail source distinguishes a confirmed-empty label list from a failed call, and only clears on the former
- [x] #3 An existing sidecar is never overwritten by a derived value; the DB is rebuilt from it instead (replaces the original #3 — see Correction)
- [x] #4 Regression test covers a message in two IMAP folders surviving update-labels intact
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sidecar-wins is the whole fix. Both paths now read the sidecar before writing: if one exists it is restored *into* the DB and the file is left alone; only an email with labels nowhere gets a derived value (IMAP folder name, or a Gmail fetch). That also makes the Gmail path cheaper — no API call for a message whose sidecar already answers.

get_labels_for_message returns `list[str] | None` now, None meaning the call failed. The two download-path callers in gmail.py take `or []` so a label hiccup still can't fail a download; update-labels counts None as an error and writes nothing, leaving the message for a later run. A confirmed `[]` is an answer and gets an empty sidecar, which is what stops the next run asking again.

Deliberately not done: connecting and re-scanning folder membership for IMAP, the other option in Fix direction. It would re-read label state from the server after capture, which doc-8 rules out, and cross-folder membership already comes from the scan at download time.

Gmail's summary line said 'Skipped (no labels)' for a counter that only ever meant 'row not in the index'. Relabelled.

Coverage: the two sidecar-survival tests and the two None-vs-empty tests were each checked against reverted behaviour and fail there.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 07:04
---
doc-8's ownership-transfer model raises the stakes here. Once local label editing lands (TASK-5.4), ownmail's labels are authoritative after capture — so update-labels re-snapshotting from the server does not merely lose multi-folder membership, it overwrites the user's own edits with a view ownmail no longer defers to.

That changes the fix direction. The question is not only 'make update-labels correct' but 'what is this command still for'. Defensible remaining scope: a one-time backfill for archives captured before sidecars/local editing existed. Ongoing re-snapshotting is at odds with the model.
---
<!-- COMMENTS:END -->
