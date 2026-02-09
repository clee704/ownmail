# ownmail

**Own your mail.** Back up your email to plain files. Search and read them offline. Own them forever.

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
ownmail backup

# 3. Search
ownmail search "invoice from:amazon"

# 4. Browse your archive in the browser
ownmail serve
```

## Philosophy

- 📁 **Files as source of truth** — Your emails are stored as standard `.eml` files. No proprietary database, no lock-in.
- 🔐 **You own your data** — Everything stays on your drive. Put it on an encrypted volume and you're done.
- ⚡ **Fast & incremental** — Only downloads new emails. Resume anytime with Ctrl-C.
- 🔍 **Optional search** — SQLite-based full-text search. The index is just a convenience layer.
- 🌐 **Built-in viewer** — Browse and read your archive in any browser. Dark mode, sanitized HTML, attachment downloads.

## Why ownmail?

There are existing tools like `mbsync` + `mu` or `offlineimap` that can accomplish similar goals. Here's why you might prefer ownmail:

| | mbsync + mu | ownmail |
|---|---|---|
| **Setup** | Configure multiple tools separately | Single `pip install`, one config file |
| **Credentials** | Plaintext in `~/.mbsyncrc` | System keychain (macOS/Windows/Linux) |
| **Providers** | IMAP only | Any IMAP server + Gmail API (OAuth) |
| **Integrity** | — | SHA256 hashes, `verify` and `sync-check` commands |
| **Web viewer** | — | Built-in browser UI with search, dark mode, HTML sanitization |
| **Hackability** | Multiple codebases in different languages | Single Python project — fork it, make it yours |

**The bottom line:** If you want a simple, single-tool email backup that stores plain files — ownmail is for you.

## Commands

| Command | Description |
|---------|-------------|
| `setup` | Set up email source credentials (App Password or OAuth) |
| `backup` | Download new emails |
| `search "query"` | Full-text search |
| `serve` | Browse and read your archive in the browser |
| `stats` | Show archive statistics |
| `verify` | Check file integrity (SHA256) |
| `sync-check` | Compare local archive with server |
| `add-labels` | Add Gmail labels to existing emails |
| `reindex` | Rebuild search index |
| `rehash` | Compute hashes for integrity verification |

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
7. Run: `ownmail setup --method oauth --credentials-file ~/Downloads/credentials.json`
8. Delete the JSON file after import

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
archive_root: /Volumes/Secure/ownmail

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
  #   exclude_folders:
  #     - Trash
  #     - Spam
```

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

### Integrity Verification

```bash
# Verify all files match their stored hashes
ownmail verify

# Compute hashes for existing emails
ownmail rehash

# Check if local matches server
ownmail sync-check
```

### Resumable Backups

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

### HTML Sanitization

When using `ownmail serve`, email HTML is sanitized server-side using [DOMPurify](https://github.com/cure53/DOMPurify) running in a Node.js sidecar process. This strips `<script>` tags, event handlers, dangerous CSS (`@import`, `expression()`), and other XSS vectors before the content reaches your browser.

**Requires [Node.js](https://nodejs.org) (v18+).** Dependencies are installed automatically on first run.

## Roadmap

- [x] IMAP support (Gmail, Outlook, Fastmail, any IMAP server)
- [x] Gmail API (OAuth, batch downloads, native labels)
- [x] Web UI for browsing and search
- [ ] Local .eml import

## License

MIT
