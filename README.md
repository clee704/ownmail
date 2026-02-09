# Gmail Archive

**A simple, file-based Gmail backup tool. No cloud. No BS. Just your emails on your drive.**

```
$ gmail_archive.py backup

Gmail Archive - Backup
==================================================

✓ Authenticated with Gmail API
Archive location: /path/to/archive
Previously backed up: 10,000 emails

Checking for new emails...

✓ No new emails to download. Archive is up to date!
```

## Why?

- 📁 **File-based** — Your emails are stored as standard `.eml` files. Open them with any email client. No proprietary formats, no lock-in.
- 🔐 **Secure by default** — OAuth credentials stored in macOS Keychain. Put your archive on an encrypted volume and you're done.
- ⚡ **Fast & incremental** — Only downloads new emails. Resume anytime with Ctrl-C.
- 🔍 **Optional search** — SQLite-based full-text search. Totally optional.

## Quick Start

```bash
# Install
pip install google-auth google-auth-oauthlib google-api-python-client keyring

# Setup (one-time)
python gmail_archive.py setup

# Backup
python gmail_archive.py backup --archive-dir /path/to/archive
```

That's it. Run `backup` whenever you want to sync new emails.

## Commands

| Command | Description |
|---------|-------------|
| `setup` | Configure OAuth credentials (stored in Keychain) |
| `backup` | Download new emails |
| `search "query"` | Search your archive |
| `stats` | Show backup statistics |
| `reindex` | Rebuild search index |

## Setup

### 1. Create Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Gmail API** (APIs & Services → Library)
4. Create **OAuth 2.0 credentials** (Credentials → Create → OAuth client ID → Desktop app)
5. Download the JSON file

### 2. Import Credentials

```bash
# Option A: Paste directly (recommended — JSON never touches disk)
python gmail_archive.py setup

# Option B: Import from file
python gmail_archive.py setup --credentials-file ~/Downloads/credentials.json
rm ~/Downloads/credentials.json  # Delete after import!
```

### 3. Backup

```bash
python gmail_archive.py backup --archive-dir /path/to/your/encrypted/volume
```

First run will open a browser for OAuth authorization. After that, it's fully automated.

## Search

```bash
# Simple search
gmail_archive.py search "invoice"

# By sender
gmail_archive.py search "from:amazon"

# By subject
gmail_archive.py search "subject:receipt"

# Attachments
gmail_archive.py search "attachment:pdf"
```

Search is powered by SQLite FTS5 — fast and works offline.

## Storage Layout

```
/path/to/archive/          # Your encrypted volume
├── archive.db                  # SQLite (tracking + search index)
└── emails/
    ├── 2024/
    │   ├── 01/
    │   │   ├── 20240115_143022_a1b2c3d4e5f6.eml
    │   │   └── ...
    │   └── 02/
    └── 2025/
        └── ...
```

- **Emails**: Standard `.eml` format. Open with Apple Mail, Thunderbird, Outlook, etc.
- **Database**: Only stores message IDs and filenames (no email content). Search index is optional.

## Resumable Backups

Downloading thousands of emails takes time. Press **Ctrl-C** anytime to pause:

```
  [1,000/10,000] Downloading and indexing...
^C

⏸ Stopping after current email...
--------------------------------------------------
Backup Paused!
  Downloaded: 1,000 emails
  Remaining: 9,000 emails

  Run 'backup' again to resume.
```

Each email is saved atomically. No corruption, no duplicates. Just run `backup` again to continue.

## Security

| What | Where |
|------|-------|
| OAuth client credentials | macOS Keychain |
| OAuth access token | macOS Keychain |
| Emails & search index | Your chosen directory |

Nothing sensitive is stored on the filesystem. Put your archive on an encrypted volume (FileVault, VeraCrypt, etc.) for full protection.

## Requirements

- Python 3.8+
- macOS (uses Keychain for credential storage)

```bash
pip install google-auth google-auth-oauthlib google-api-python-client keyring
```

## FAQ

**Can I run this on Linux?**  
The `keyring` library supports Linux keyrings, but it's untested. PRs welcome!

**What if I delete an email from Gmail?**  
It stays in your backup. This is an archive, not a sync.

**How do I restore emails to Gmail?**  
Import the `.eml` files through any email client that supports IMAP.

**Is this affiliated with Google?**  
No. This uses the official Gmail API but is an independent open source project.

## License

MIT
