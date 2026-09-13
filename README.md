# ownmail

**Own your mail.** Back up your email to plain files. Search and read them offline. Own them forever.

```
$ ownmail download

ownmail - Download
==================================================

✓ Authenticated with Gmail API
Archive location: /path/to/archive
Previously downloaded: 10,000 emails

Checking for new emails...

✓ No new emails to download. Archive is up to date!
```

## Install

```bash
pip install ownmail
# or
pipx install ownmail
```

## Quick Start

```bash
# 1. Set up credentials (one-time)
ownmail setup

# 2. Download your emails
ownmail download

# 3. Search
ownmail search "invoice from:amazon"

# 4. Browse your archive in the browser
ownmail serve
```

## Philosophy

- 📁 **Files as source of truth** — Your emails are stored as standard `.eml` files. No proprietary database, no lock-in.
- 🔐 **You own your data** — Everything stays on your drive. Put it on an encrypted volume and you're done.
- ⚡ **Fast & incremental** — Only downloads new emails. Resume anytime with Ctrl-C.
- 🔍 **Full-text search** — SQLite FTS5-backed search. Fast, local, private.
- 🌐 **Built-in viewer** — Browse and read your archive in any browser. Dark mode, sanitized HTML, attachment downloads.

## Why ownmail?

Tools like `mbsync` + `notmuch` can accomplish similar goals — `mbsync` syncs IMAP to a local Maildir, and `notmuch` indexes it for fast tag-based search. They're powerful and battle-tested. Here's how ownmail differs:

| | mbsync + notmuch | ownmail |
|---|---|---|
| **What it is** | Two separate tools (sync + index) | Single tool: backup, search, browse |
| **Setup** | Configure `mbsync` and `notmuch` separately | `pip install ownmail && ownmail setup` |
| **Credentials** | Plaintext in `~/.mbsyncrc` | System keychain (macOS/Windows/Linux) |
| **Storage format** | Maildir (flags in filenames) | `.eml` files organized by date |
| **Search engine** | Xapian (tag-based, very fast) | SQLite FTS5 (good enough for most archives) |
| **Reading email** | Emacs, Vim, mutt, or other frontends | Built-in web UI |
| **Providers** | IMAP only | IMAP + Gmail API (OAuth, batch downloads) |
| **Integrity checking** | — | Detects corrupted or missing files |
| **Philosophy** | Power-user toolkit, compose your workflow | Opinionated single tool — backup, search, done |

**Choose mbsync + notmuch** if you already live in Emacs/mutt and want maximum flexibility.

**Choose ownmail** if you want a simple, self-contained email backup that stores plain files and lets you search and read them in a browser.

## Commands

| Command | Description |
|---------|-------------|
| `setup` | Set up email source credentials (App Password or OAuth) |
| `download` | Download new emails (with content-hash dedup) |
| `search "query"` | Full-text search |
| `serve` | Browse and read your archive in the browser |
| `import <path>` | Import external `.eml` files (Tuta, Thunderbird, any export) |
| `scan` | Register `.eml` files already in the archive but untracked |
| `stats` | Show archive statistics |
| `verify` | Check file integrity (hashes, moved files, orphans, DB health) |
| `sync-check` | Compare local archive with server to find missing emails |
| `trash` | View and manage trashed emails |
| `update-labels` | Update labels on existing emails |
| `relabel` | Repair IMAP folder labels on archived mail by rescanning the server |
| `reconcile` | Find archived mail the current download filter would now reject |
| `rebuild` | Rebuild search index and populate metadata |
| `reset-sync` | Reset sync state to force full re-download |
| `list-unknown` | List emails with unparseable dates |
| `sources list` | List configured email sources |

Run `ownmail <command> --help` for the full options on any of these.

## Setup

ownmail supports two methods for connecting to your email:

### Option A: IMAP with App Password (recommended)

The simplest way to get started. Works with Gmail, Outlook, Fastmail, and any IMAP server.

**For Gmail:**

1. Enable [2-Step Verification](https://myaccount.google.com/signinoptions/two-step-verification) (if not already)
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Create an App Password (name it "ownmail")
4. Run setup:

```bash
ownmail setup
# Choose [1] IMAP with App Password
# Enter your Gmail address and the 16-character App Password
```

That's it. Credentials are stored in your system keychain.

> **"The setting you are looking for is not available for your account"?**
> This means 2-Step Verification isn't enabled yet (step 1 above), or your Google Workspace admin has disabled App Passwords. For Workspace accounts where App Passwords are blocked, use [Option B (OAuth)](#option-b-gmail-api-with-oauth-advanced) instead.

**For other IMAP servers** (Fastmail, company mail, etc.), the same flow works — you'll be prompted for the IMAP hostname.

### Option B: Gmail API with OAuth (advanced)

Uses the Gmail API with read-only OAuth scope. Faster batch downloads and native Gmail labels, but requires creating a Google Cloud project.

```bash
ownmail setup --method oauth
```

<details>
<summary>Detailed steps</summary>

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. APIs & Services → Library → search "Gmail API" → Enable
4. APIs & Services → Credentials → Create Credentials → OAuth client ID
5. Application type: Desktop app → Create
6. Download the JSON file
7. Run: `ownmail setup --method oauth`
8. When prompted, enter the path to the downloaded JSON file (or paste its contents)

</details>

### Comparison

| | IMAP + App Password | Gmail API + OAuth |
|---|---|---|
| **Setup time** | 30 seconds | ~15 minutes |
| **Requires** | 2FA enabled | Google Cloud project |
| **Access scope** | Full account | Read-only |
| **Revocable** | Yes (App Passwords page) | Yes (Google Account) |
| **Speed** | Sequential (one at a time) | Batch downloads |
| **Gmail labels** | Mapped from IMAP folders | Native labels |
| **Works with** | Gmail, Outlook, Fastmail, any IMAP | Gmail only |
| **Credentials stored in** | System keychain | System keychain |

## Config File

Create `config.yaml` in your working directory:

```yaml
archive_root: /path/to/archive

sources:
  # Option A: IMAP with App Password (recommended)
  - name: gmail_personal
    type: imap
    host: imap.gmail.com
    account: you@gmail.com
    auth:
      secret_ref: keychain:imap-password/you@gmail.com

  # Option B: Gmail API with OAuth
  # - name: gmail_personal
  #   type: gmail_api
  #   account: you@gmail.com
  #   auth:
  #     secret_ref: keychain:oauth-token/you@gmail.com
  #   include_labels: true

  # Other IMAP servers
  # - name: work_imap
  #   type: imap
  #   host: imap.company.com
  #   account: you@company.com
  #   auth:
  #     secret_ref: keychain:imap-password/you@company.com
  #   exclude_roles: [inbox]    # optional — see below
  #   exclude_folders:          # optional — see below
  #     - Newsletters
```

### What gets archived

ownmail archives mail you have finished with, not everything on the server.
A message is downloaded once it is out of the **inbox**, **drafts**,
**trash** and **spam** — whatever your provider calls those folders, since
ownmail asks the server (IMAP SPECIAL-USE) rather than matching names.

The idea is that your mail client owns triage. Inbox means you haven't
decided yet; drafts means the message isn't finished; trash and spam mean a
decision was made that it isn't worth keeping. **Sent mail is archived** —
there's no triage step for your own outgoing mail, so waiting for one would
mean never archiving it.

Nothing is written off. Every run re-checks where a message is now, so mail
you rescue from spam, file out of the inbox, or send from a draft is picked
up on the next run.

`exclude_roles` relaxes the first two — `[inbox]` archives your drafts,
`[]` archives both as they arrive. Trash and spam are always excluded and
naming them is a config error. `exclude_folders` skips extra folders by
name, on top of the roles rather than instead of them.

### Reconciling what is already archived

The filter decides what comes *in*. Narrowing it — or upgrading from a
version that couldn't recognize your server's trash folder — leaves mail in
the archive the filter would reject today. `reconcile` finds it:

```bash
# Report what the current filter would no longer admit
ownmail reconcile

# Move it to ownmail's bin, where it stays restorable until you empty it
ownmail reconcile --apply
```

It reads the filter from your config, so editing `exclude_roles` or
`exclude_folders` changes what it reports. Mail carrying a real label
alongside the rejected one was filed somewhere, so it is listed separately
and left alone. Nothing moves without `--apply`, and nothing is deleted.

## Search

```bash
ownmail search "invoice"
ownmail search "from:amazon"
ownmail search "subject:receipt"
ownmail search "attachment:pdf"
```

## Security

| What | Where |
|------|-------|
| App Passwords & OAuth tokens | System keychain (macOS/Windows/Linux) |
| Emails & search index | Your chosen directory |

Nothing sensitive on the filesystem. Put your archive on an encrypted volume.

## Advanced

### Storage Layout

```
/path/to/archive/
├── ownmail.db              # SQLite (tracking + search index)
└── sources/
    └── gmail_personal/
        ├── 2024/
        │   ├── 01/
        │   │   ├── 20240115_143022_a1b2c3d4e5f6.eml
        │   │   └── ...
        │   └── 02/
        └── 2025/
            └── ...
```

- **Emails**: Standard `.eml` format, organized by account and date
- **Database**: Stores metadata (message IDs, filenames, hashes, subjects, senders) and a full-text search index — the `.eml` files are the source of truth

### Integrity Verification

```bash
# Verify file hashes, detect moved files, check for orphans and DB health
ownmail verify

# Auto-fix: update moved file paths, remove stale entries, rebuild FTS
ownmail verify --fix

# Check if local archive matches server
ownmail sync-check
```

### Repairing Legacy Labels

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

### Resumable Downloads

Press **Ctrl-C** anytime to pause:

```
  [1,000/10,000]   45KB - indexing...
^C

⏸ Stopping after current email...
--------------------------------------------------
Download Paused!
  Downloaded: 1,000 emails
  Remaining: 9,000 emails

  Run 'download' again to resume.
```

### HTML Sanitization

When using `ownmail serve`, email HTML is sanitized server-side using [DOMPurify](https://github.com/cure53/DOMPurify) running in a Node.js sidecar process. This strips `<script>` tags, event handlers, dangerous CSS (`@import`, `expression()`), and other XSS vectors before the content reaches your browser.

**Requires [Node.js](https://nodejs.org) (v18+).** Dependencies are installed automatically on first run.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup and repo conventions, and
[AGENTS.md](AGENTS.md) if you're pointing an AI coding agent at this repo.
Planned and in-flight work lives in [`backlog/`](backlog/tasks) — browse it with
the [Backlog.md](https://github.com/MrLesk/Backlog.md) CLI.

## License

MIT
