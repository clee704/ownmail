# ownmail

**Own your mail.** A file-based email backup and search tool. Your emails, your files, your drive.

> **Note:** ownmail is a backup tool, not an email client. It downloads and archives your emails for safekeeping and search — it doesn't send, receive, or manage your inbox. For that, keep using Gmail, Outlook, or your favorite mail app.

```
$ ownmail backup

ownmail - Backup
==================================================

✓ Authenticated with Gmail API
Archive location: /Volumes/Secure/ownmail
Previously backed up: 12,847 emails

Checking for new emails...

✓ No new emails to download. Archive is up to date!
```

## Philosophy

- 📁 **Files as source of truth** — Your emails are stored as standard `.eml` files. No proprietary database, no lock-in.
- 🔐 **You own your data** — Everything stays on your drive. Put it on an encrypted volume and you're done.
- ⚡ **Fast & incremental** — Only downloads new emails. Resume anytime with Ctrl-C.
- 🔍 **Optional search** — SQLite-based full-text search. The index is just a convenience layer.

## Why ownmail?

There are existing tools like `mbsync` + `mu` or `offlineimap` that can accomplish similar goals. Here's why you might prefer ownmail:

| | mbsync + mu | ownmail |
|---|---|---|
| **Setup** | Configure multiple tools separately | Single `pip install`, one config file |
| **Credentials** | Plaintext in `~/.mbsyncrc` | System keychain (macOS/Windows/Linux) |
| **Gmail sync** | IMAP (slower, label limitations) | Gmail API (fast, proper labels, history-based sync) |
| **Integrity** | — | SHA256 hashes, `verify` and `sync-check` commands |
| **Hackability** | Multiple codebases in different languages | Single Python project — fork it, make it yours |

**The bottom line:** If you're already comfortable with mbsync + mu, you probably don't need this. But if you want something simpler that "just works" for Gmail backup, or you want a single codebase you can easily modify to your taste — ownmail is for you.

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

# 2. Backup your emails
ownmail backup --archive-dir /Volumes/Secure/ownmail

# 3. Search
ownmail search "invoice from:amazon"
```

## Commands

| Command | Description |
|---------|-------------|
| `setup` | Configure OAuth credentials (stored in Keychain) |
| `backup` | Download new emails |
| `search "query"` | Full-text search |
| `stats` | Show archive statistics |
| `verify` | Check file integrity (SHA256) |
| `sync-check` | Compare local archive with server |
| `add-labels` | Add Gmail labels to existing emails |
| `reindex` | Rebuild search index |
| `rehash` | Compute hashes for integrity verification |

## Setup

### 1. Create Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Gmail API** (APIs & Services → Library)
4. Create **OAuth 2.0 credentials** (Credentials → Create → OAuth client ID → Desktop app)
5. Download the JSON file

### 2. Import Credentials

```bash
# Option A: Paste directly (recommended — never touches disk)
ownmail setup

# Option B: Import from file
ownmail setup --credentials-file ~/Downloads/credentials.json
rm ~/Downloads/credentials.json  # Delete after import!
```

Credentials are stored in your system keychain (macOS Keychain, Windows Credential Manager, or Linux Secret Service), never on the filesystem.

## Config File

Create `config.yaml` in your working directory:

```yaml
archive_root: /Volumes/Secure/ownmail

sources:
  - name: gmail_personal
    type: gmail_api
    account: you@gmail.com
    auth:
      secret_ref: keychain:gmail_personal_token
    include_labels: true

  # Add more sources as needed:
  # - name: work_imap
  #   type: imap
  #   host: imap.company.com
  #   account: you@company.com
  #   auth:
  #     secret_ref: keychain:work_imap_password
```

## Search

```bash
ownmail search "invoice"
ownmail search "from:amazon"
ownmail search "subject:receipt"
ownmail search "attachment:pdf"
```

## Storage Layout

```
/Volumes/Secure/ownmail/
├── ownmail.db              # SQLite (tracking + search index)
└── emails/
    ├── 2024/
    │   ├── 01/
    │   │   ├── 20240115_143022_a1b2c3d4e5f6.eml
    │   │   └── ...
    │   └── 02/
    └── 2025/
        └── ...
```

- **Emails**: Standard `.eml` format with `X-Gmail-Labels` header
- **Database**: Only stores message IDs, filenames, and hashes — not email content

## Integrity Verification

```bash
# Verify all files match their stored hashes
ownmail verify

# Compute hashes for existing emails
ownmail rehash

# Check if local matches server
ownmail sync-check
```

## Resumable Backups

Press **Ctrl-C** anytime to pause:

```
  [1,342/15,000]   45KB - indexing...
^C

⏸ Stopping after current email...
--------------------------------------------------
Backup Paused!
  Downloaded: 1,342 emails
  Remaining: 13,658 emails

  Run 'backup' again to resume.
```

## Security

| What | Where |
|------|-------|
| OAuth credentials | System keychain (macOS/Windows/Linux) |
| Emails & search index | Your chosen directory |

Nothing sensitive on the filesystem. Put your archive on an encrypted volume.

### HTML Sanitization

When using `ownmail serve`, email HTML is sanitized server-side using [DOMPurify](https://github.com/cure53/DOMPurify) running in a Node.js sidecar process. This strips `<script>` tags, event handlers, dangerous CSS (`@import`, `expression()`), and other XSS vectors before the content reaches your browser.

**Requires [Node.js](https://nodejs.org) (v18+).** Dependencies are installed automatically on first run. If Node.js is not available, the web UI still works — the iframe sandbox provides baseline protection.

## Roadmap

- [ ] Multiple accounts
- [ ] Outlook/Microsoft 365 support
- [ ] Generic IMAP support
- [ ] Web UI for self-hosted access

## License

MIT
