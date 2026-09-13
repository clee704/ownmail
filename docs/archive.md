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
