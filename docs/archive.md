# Archive storage and maintenance

[Back to README](../README.md)

## Storage

Ownmail stores messages as standard `.eml` files, organized by source and date.
JSON sidecars retain labels alongside those files. SQLite stores a searchable
index and download progress.

```text
archive/
├── ownmail.db
└── sources/
    └── personal/
        └── 2026/
            └── 01/
                ├── 20260115_143022_a1b2c3d4e5f6.eml
                └── 20260115_143022_a1b2c3d4e5f6.json
```

This is a synthetic layout. Preserve both message files and sidecars in backups;
the database can be rebuilt from the archive. Keep a copy of your configuration
as well. These files can contain sensitive information; ownmail does not encrypt
them. A separate `db_dir` can place the index on a faster drive while the archive
stays on external storage.

## Editing labels

Open a message, choose **More message actions → Edit labels**, add or remove
individual labels, and select **Save labels**. Removing every label saves an
intentional empty set. Label names retain punctuation and whitespace.

Edits apply to the owned copy and never update a server label. The editor shows
the exact saved names, including historical `INBOX` and `DRAFT` labels that
navigation hides. Exact `UNREAD` is reserved for mail-client state and must be
removed before saving. Other system labels may be grouped in navigation.

The sidecar is saved atomically before the search index is updated. If the
editor reports that labels were saved but search could not be updated, save
again to retry indexing. `ownmail rebuild --only sidecars` also restores the
index from saved sidecars. Downloads, `update-labels`, and rebuilds preserve
edited labels, including an empty set. An unreadable existing sidecar blocks
editing so its other metadata cannot be discarded.

## Download filters

By default, messages in **Inbox**, **Drafts**, **Trash**, or **Spam** are not
downloaded. Sent mail is eligible. Gmail labels and IMAP server-provided folder
roles identify these categories. Later downloads reconsider eligible mail when
it is filed out of the inbox, sent from drafts, or rescued from spam.

Set `exclude_roles` per source to adjust inbox and draft capture:

| Value | Effect |
|---|---|
| `[inbox, drafts]` | Default: exclude inbox mail and drafts |
| `[inbox]` | Include drafts, exclude inbox mail |
| `[drafts]` | Include inbox mail, exclude drafts |
| `[]` | Include both inbox mail and drafts |

Trash and spam are always excluded; naming them in `exclude_roles` is a
configuration error. `exclude_folders` adds exclusions for specific IMAP folder
names. See [config.example.yaml](../config.example.yaml) for examples and rescan
behavior after filter changes.

Gmail captures labels by default. If a required label lookup fails, the message
remains uncaptured and a later download retries it; other messages can still
finish. A confirmed empty label set is valid. Setting `include_labels: false`
explicitly omits Gmail labels and saves an empty label sidecar. Downloads never
refresh the labels of an already archived copy.

### Thread protection for server cleanup

Eligible messages enter the archive immediately, including replies in an ongoing
conversation. The provider's read-only thread check is separate from capture.
It holds cleanup eligibility while the candidate or another thread member is in
Inbox or unfinished outgoing state. Trash and Spam members do not hold the
thread. An active thread has no expiry or age override. A later reply protects
copies still present; the check never restores removed copies or updates an
archived message's contents or labels.

Cleanup is not enabled yet. The thread check supplies current identity, roles,
observation time, completeness, and a revision when available for the planned
cleanup command. That command
must repeat the check before each mutation, including across batches. Capture
filters and configured label omission never hide members from this check.

Provider limits:

- **Gmail API:** re-read the candidate and its complete thread with the existing
  read-only authorization. Changed, malformed, missing, or failed responses hold
  cleanup. Inbox and Draft labels prove activity; Sent proves completion.
  Google's public API documentation does not establish a reliable Scheduled-mail
  state, so other members without a confirmed finished state keep cleanup held.
  This also holds ordinary received/filed threads; broad cleanup of those
  threads remains unavailable. See Google's [label behavior](https://developers.google.com/workspace/gmail/api/guides/labels)
  and [Scheduled mail](https://support.google.com/mail/answer/9214606?hl=en).
- **Gmail over IMAP:** cleanup stays held. Native thread identifiers establish
  grouping, but configurable folder-size limits can hide members. A successful
  visible-folder scan cannot prove an inactive account-wide thread. See the
  [IMAP extensions](https://developers.google.com/workspace/gmail/imap/imap-extensions)
  and [visibility settings](https://developers.google.com/workspace/gmail/api/reference/rest/v1/ImapSettings).
- **Standard IMAP, including mailbox.org:** cleanup stays held. Message-ID and
  References headers cannot establish complete account-wide thread membership;
  the [IMAP THREAD extension](https://www.rfc-editor.org/rfc/rfc5256.html) operates
  within a selected mailbox. Missing or partial results never establish that a
  thread has cleared.

Even a complete Gmail response is an observation, not a lock. The
[Trash API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash)
has no conditional thread-revision parameter; activity can change after a final
check and before a future Trash request. No atomic cleanup guarantee is made.

### Reconciling existing mail

Changing a download filter does not remove already archived messages. Review
which messages the current filter would reject:

```bash
ownmail reconcile
```

To move the reported messages to the archive's restorable Trash:

```bash
ownmail reconcile --apply
```

Messages carrying a real label alongside the rejected one are reported separately
and left alone. The command does not move messages without `--apply`, and it does
not permanently delete them.

## Imports and resumable downloads

Import external `.eml` exports, or register files already inside the archive:

```bash
ownmail import /path/to/export
ownmail scan
```

Run `ownmail <command> --help` for source selection and dry-run options.
Downloads commit progress in batches. Press Ctrl-C to stop, then run
`ownmail download` again to resume.

## Integrity verification

```bash
# Check file hashes, moved files, orphans, and database health
ownmail verify

# Repair index paths and stale entries, and rebuild full-text search
ownmail verify --fix

# Compare the local archive with its configured mail sources
ownmail sync-check
```

See `ownmail verify --help` and `ownmail rebuild --help` for available checks and
rebuild modes.

## Repairing legacy labels

Older releases could append message IDs from a folded `References` header to
the `SENT` label. From a source checkout, preview the affected metadata with:

```bash
python scripts/repair_labels.py --archive /path/to/archive
```

Add `--database /path/to/ownmail.db` if the index is stored separately. Stop
downloads and other archive maintenance before applying a repair, and provide
a directory for the original metadata backups:

```bash
python scripts/repair_labels.py --archive /path/to/archive \
  --apply --backup-dir /path/to/label-repair-backup
```

The repair requires an exact match to the message's folded header and a valid
recorded file hash. It updates the JSON sidecar and database labels, preserves
other sidecar fields, and leaves `.eml` files unchanged. Interrupted repairs can
be rerun with the same backup directory. Values without matching evidence are
left for inspection; long names and names containing angle brackets are not
rejected on appearance alone.

Labels retain commas and whitespace during capture, indexing, and rebuilding.
For example, `label:"Receipts, 2026"` searches for one label. Rebuilding uses
sidecar labels when available and preserves indexed labels otherwise. Labels
already split by older code can be restored from an intact sidecar with
`ownmail rebuild --only sidecars`. Without the original sidecar, the intended
label boundaries cannot be recovered reliably from the index alone.
