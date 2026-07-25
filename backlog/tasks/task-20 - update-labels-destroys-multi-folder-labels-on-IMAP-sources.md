---
id: TASK-20
title: update-labels destroys multi-folder labels on IMAP sources
status: To Do
assignee: []
created_date: '2026-07-25 06:49'
updated_date: '2026-07-25 07:04'
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
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 update-labels on an IMAP source no longer reduces a multi-folder message to a single label
- [ ] #2 update-labels on a Gmail source distinguishes a confirmed-empty label list from a failed call, and only clears on the former
- [ ] #3 A message whose labels were all removed on the server has them cleared locally rather than kept stale
- [ ] #4 Regression test covers a message in two IMAP folders surviving update-labels intact
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 07:04
---
doc-8's ownership-transfer model raises the stakes here. Once local label editing lands (TASK-5.4), ownmail's labels are authoritative after capture — so update-labels re-snapshotting from the server does not merely lose multi-folder membership, it overwrites the user's own edits with a view ownmail no longer defers to.

That changes the fix direction. The question is not only 'make update-labels correct' but 'what is this command still for'. Defensible remaining scope: a one-time backfill for archives captured before sidecars/local editing existed. Ongoing re-snapshotting is at odds with the model.
---
<!-- COMMENTS:END -->
