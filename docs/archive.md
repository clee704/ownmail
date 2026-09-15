# Archive storage and maintenance

[Back to README](../README.md)

## Storage

Ownmail stores messages as standard `.eml` files, organized by source and date.
JSON sidecars retain labels alongside those files. SQLite stores a searchable
index.

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

Active mail has separate, disposable storage. By default, an archive named
`archive` uses the sibling directory `.archive-active`. Set the top-level
`active_cache_dir` to use another directory. It must be outside the archive,
must not contain the archive, and must be empty or an existing ownmail cache for
that archive. Relative paths use the working directory.

The cache contains message files, JSON metadata and refresh status, and its own
rebuildable search index. It can be recreated from mail still on the server;
its presence never makes a message archived or eligible for server cleanup.
Existing archive files, sidecars, database schema, and local Trash stay unchanged.

## Editing labels

Open an archived message, choose **More message actions → Edit labels**, add or
remove individual labels, and select **Save labels**. Removing every label saves an
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
Cached Active messages have no local label editor or local Trash action. Manage
them in the mail client.

## Download filters

Downloads cache **Inbox**, **Drafts**, other observed unfinished mail, and
messages with unconfirmed state by default.
Active copies follow confirmed server edits. Confirmed deletion, Trash, or Spam
retires the cached copy after a complete server listing with no failed message
reads. Failed or partial listings defer removals and show unconfirmed freshness.
Trash and Spam take precedence over Inbox or unfinished outgoing state, which
takes precedence over Sent or filing labels.

Ordinary filed and Sent mail can enter the archive after a fresh current-state
check finds no Active, discarded, or unrecognized state. Capture completes only
when the contents and configured label snapshot have been saved successfully.
Unrecognized states and failed checks hold the affected message for a later run.

| Provider | Active and unfinished-state detection | Capture eligibility |
|---|---|---|
| Gmail API | Current `INBOX` and `DRAFT` labels | Filed and Sent mail with recognized system labels or verified user labels is eligible. Unknown system labels and failed required label-catalog reads hold affected messages. |
| Gmail over IMAP | Current Gmail labels, `\Draft`, advertised `\Scheduled` folder membership, and `$SubmitPending` | Filed and Sent mail is eligible after complete identity, flag, and label reads. Unrecognized system labels, mailbox attributes, or keywords remain held. |
| Standard IMAP | Inbox/Drafts folder roles, `\Draft`, advertised `\Scheduled`, and `$SubmitPending` | Other successfully checked mail is eligible. Unrecognized mailbox attributes or keywords remain held. |

Gmail's unread, starred, important, category, and verified user labels do not
make a message Active. The published [Message schema](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages#Message)
has no dedicated Scheduled field, and ownmail has not verified Gmail's Scheduled
API semantics. Capture and refresh operate on the state visible to the provider;
they cannot guarantee detection of hidden or unadvertised unfinished states.

IMAP's [`\Scheduled` attribute](https://www.rfc-editor.org/rfc/rfc9979.html#section-8.2)
and [`$SubmitPending` keyword](https://www.rfc-editor.org/rfc/rfc5550.html#section-5.10)
keep a message Active without assigning it a Drafts role. `$SubmitPending` wins
even when `$Submitted` or Sent is also present. Folder names such as `Outbox` or
`Submission` alone do not establish these roles. The nonstate keywords
`$Forwarded`, `$Submitted`, `$MDNSent`, and `$Important` are accepted
case-insensitively; other unknown keywords remain held. Optional server
attributes only describe state the server advertises. A Gmail IMAP label spelled
`\Scheduled` alone stays unconfirmed; ownmail recognizes the advertised folder
attribute and checks membership through the message's immutable Gmail ID.

Set `active_downloads: false` on a source to stop fetching Active contents while
continuing eligible capture. Changing this setting retains prior cached data and
marks the view stale; it never turns Inbox or unfinished outgoing mail into
owned copies. Confirmed capture or removal can still retire cached copies.

`exclude_roles` is deprecated for the new download lifecycle. Existing values
(`[]`, `[inbox]`, `[drafts]`, or `[inbox, drafts]`) remain accepted, but none
allows Inbox or Drafts into the archive. Trash and Spam remain excluded;
naming them in `exclude_roles` is still a configuration error. IMAP
`exclude_folders` stops downloads from exact folder names while metadata checks
continue; excluding folders leaves the overall view incomplete.

Gmail captures labels by default. If a required label lookup fails, the message
remains uncaptured and a later download retries it; other messages can still
finish. A confirmed empty label set is valid. Setting `include_labels: false`
explicitly omits Gmail labels and saves an empty label sidecar. Downloads never
refresh the labels of an already archived copy.

Capture requires a fresh, identity-matched read that confirms eligibility from
observed state and a successful save of the contents and configured label
snapshot. An unrelated listing or folder failure can leave the Active view
incomplete while a confirmed message is captured. Failed candidate state,
content, label, or storage operations remain retryable. Each successful capture
freezes the owned snapshot. Thread activity affects cleanup, never capture.
Capture sidecars retain identity and capture time so `scan` and rebuilds can
restore the index. A newly captured message without a usable Date header uses
its capture time for search ordering; the original message headers stay intact.

### Refreshing and searching Active mail

`ownmail download`, **Settings → Downloads → Download now**, and scheduled web
downloads run the same lifecycle. Scheduling uses the existing
`web.download_interval_minutes` setting and defaults to Off; see
[browser downloads](../README.md#download-from-the-browser).

Every run enumerates metadata for all mail visible to the provider, including
Trash and Spam for state checks. This can take longer than an incremental pass
on large accounts. Verified finished copies already owned can skip content
fetching. Date filters constrain capture while the Active refresh still examines
all visible mail; a date-filtered run is marked incomplete.

Ordinary search includes Active and Archived mail. `is:active` selects cached
live copies, including unconfirmed states; `is:archived` selects owned copies.
Unknown `is:` values are search errors. An owned message that returns to Inbox
keeps its contents, labels, and local Trash state. Verified live/owned matches
produce one ordinary result, with links between the archived and cached content.
Historical `INBOX` or `DRAFT` labels alone never establish current Active state.

Active rows and the reader show the last check time. Incomplete or disabled
refreshes keep that age visible and mark the state unconfirmed. The Active
sidebar counts cached entries, including stale entries and entries with an owned
match; consolidation can produce fewer search results. Download status reports
archived and Active-refreshed counts separately. A completed archive pass does
not establish that the Active view is current.

## Server cleanup

Cleanup is a separate, optional command. Downloads and scheduled downloads never
run it. Select one configured source; preview is the default:

```bash
ownmail cleanup --source personal
```

The sweep includes previously archived messages and reports each outcome with
its reason and check time. It reads the existing index, including a configured
`db_dir`, without creating or rebuilding it. Eligibility requires all of these:

1. A current owned `.eml` and readable sidecar stored as regular files in the
   selected source, with matching hashes, source/account identity, and durable evidence
   that the required capture metadata was saved.
2. A matching authenticated Gmail account and a fresh server message whose
   identity and raw contents correspond to the owned copy.
3. Current message and complete thread checks that show no Active or
   unrecognized state. A candidate already in Trash or Spam stays held.
4. A final local check after the server reads, confirming the owned copy still
   qualifies immediately before an apply request.

Active caches, local Trash, missing or changed copies, and incomplete capture
metadata never qualify. Legacy sidecars without evidence of a complete capture
remain held, even if their label list is empty. Cleanup does not replace local
labels with server labels or modify owned files. IMAP candidates remain held
without connecting to the server because complete thread visibility is unavailable.

### Applying and retrying

Existing Gmail sign-in requests `gmail.readonly`, which supports previews.
Gmail's [Trash method](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash)
requires `gmail.modify` or broader authorization. A separate cleanup consent
flow is not implemented. `--apply` does not widen permissions; with the current
read-only login, Gmail rejects the move and cleanup reports the denial.

With suitable Gmail authorization, explicitly request apply:

```bash
ownmail cleanup --source personal --apply
```

Apply moves eligible Gmail messages to server Trash and never hard-deletes.
Individual verification failures are reported while other candidates continue.
An account-verification failure or denied apply request stops that source's run.
The summary separates eligible, held, confirmed Trash moves, and errors.

After an interruption or uncertain response, rerun the command. Each attempt
rechecks local evidence and current remote state, so copies already in Trash
are skipped. The Trash request has no automatic retry, and an unconfirmed
response is not reported as a successful move. Preview results reflect their
check time; a later apply rechecks all conditions.

### Thread protection for server cleanup

Eligible messages enter the archive immediately, including replies in an ongoing
conversation. The provider's read-only thread check is separate from capture.
It holds cleanup eligibility while the candidate or another thread member is in
Inbox or unfinished outgoing state. Trash and Spam members do not hold the
thread. An active thread has no expiry or age override. A later reply protects
copies still present; the check never restores removed copies or updates an
archived message's contents or labels.

The thread check supplies current identity, roles, observation time,
completeness, and a revision when available. Cleanup repeats the check before
each mutation, including across batches. Capture filters and configured label
omission never hide members from this check.

Provider limits:

- **Gmail API:** re-read the candidate and its complete thread with the existing
  read-only authorization. Changed, malformed, missing, or failed responses hold
  cleanup eligibility. Inbox and Draft labels establish observed activity;
  successfully checked filed and Sent members can clear it. Unknown system
  labels and failed required label-catalog reads keep the thread held. The
  Scheduled API observation limit above also applies to thread checks. See
  Google's [label behavior](https://developers.google.com/workspace/gmail/api/guides/labels)
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
  thread has cleared. [Special-use folder roles](https://www.rfc-editor.org/rfc/rfc6154.html#section-2)
  are optional, and Drafts can describe where clients should save drafts.
  An empty advertised Drafts folder does not prove that outgoing work is finished.

Even a complete Gmail response is an observation, not a lock. The
[Trash API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash)
has no conditional thread-revision parameter; activity can change after a final
check and before the Trash request. No atomic cleanup guarantee is made.

### Provider Trash behavior

Moving a server copy to Trash does not guarantee reclaimed storage or permanent
removal. Only Gmail API has an apply path; IMAP remains held.

- **Gmail:** Google documents permanent deletion after 30 days in Trash. Draft
  deletion has different recovery behavior, reinforcing the requirement to
  protect unfinished mail. See [Gmail deletion and recovery](https://support.google.com/mail/answer/7401?hl=en).
- **mailbox.org:** email is not automatically deleted while the account exists,
  except from Trash when automatic deletion is configured. Mail clients can
  apply their own deletion settings. There is no universal Trash retention
  interval. See [mailbox.org's retention policy](https://kb.mailbox.org/en/private/e-mail/will-e-mails-get-deleted-automatically/).
- **Other IMAP providers:** the `\Trash` role specifies intended folder use,
  without a retention guarantee. Verify the provider's policy before enabling
  its cleanup path.

IMAP identity also needs more than a stored folder and UID: UIDs are scoped to
the account, mailbox, and UIDVALIDITY. Moves require new correspondence evidence
unless a supported extension supplies persistent identity. See
[IMAP identity](https://www.rfc-editor.org/rfc/rfc9051.html#section-2.3.1.1) and
[OBJECTID](https://www.rfc-editor.org/rfc/rfc8474.html#section-1).
An advertised [UID MOVE command](https://www.rfc-editor.org/rfc/rfc6851.html#section-3.3)
can move a message to a verified Trash destination, but it cannot establish
thread eligibility or retention. Generic flag-and-expunge behavior is unsuitable:
Gmail's [IMAP settings](https://developers.google.com/workspace/gmail/api/reference/rest/v1/ImapSettings)
can make expunging the last visible copy archive, trash, or permanently delete it.

## Reconciling existing mail

Changing Active settings does not remove already archived messages. The separate
`reconcile` command reviews archived mail against legacy role and folder filters:

```bash
ownmail reconcile
```

To move the reported messages to the archive's restorable Trash:

```bash
ownmail reconcile --apply
```

Messages carrying a real label alongside the rejected one are reported separately
and left alone. The command does not move messages without `--apply`, and it does
not permanently delete them or convert them to Active cache entries.

## Imports and resumable downloads

Import external `.eml` exports, or register files already inside the archive:

```bash
ownmail import /path/to/export
ownmail scan
```

Run `ownmail <command> --help` for source selection and dry-run options.
Downloads preserve completed saves. Press Ctrl-C to stop, then run
`ownmail download` again to retry unfinished work. An interrupted Active refresh
retains prior copies and remains incomplete.

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
