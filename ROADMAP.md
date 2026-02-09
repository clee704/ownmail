# ownmail Roadmap

## Vision

**ownmail** is a file-first email backup tool. Your emails are stored as standard `.eml` files that you own and control. The database is just an index — the files are the source of truth.

---

## v0.1.0 (Current)

- [x] Gmail backup via OAuth2
- [x] Incremental sync (Gmail History API)
- [x] Full-text search (SQLite FTS5)
- [x] Gmail labels as X-Gmail-Labels header
- [x] Integrity verification (SHA256 hashes)
- [x] Secure credential storage (macOS/Windows/Linux via keyring)
- [x] Resumable backups (Ctrl-C safe)
- [x] Resumable reindex (hash-based change detection)
- [x] Config file support
- [x] Database integrity check and repair (db-check)

---

## v0.2.0 — Multiple Accounts & Providers

**Goal**: Support multiple email accounts from different providers in the same archive.

### Providers (Priority Order)

| Provider | Protocol | Status | Notes |
|----------|----------|--------|-------|
| Gmail | OAuth2 + REST API | ✅ v0.1 | |
| Generic IMAP | IMAP + App Password | 🎯 v0.2 | Covers most providers |
| Outlook/M365 | OAuth2 + MS Graph | 📋 v0.3 | |

### Directory Structure

```
/Volumes/Secure/ownmail/
├── ownmail.db                    # Global index (all accounts)
├── accounts/
│   ├── alice@gmail.com/
│   │   └── emails/
│   │       └── 2024/...
│   ├── me@fastmail.com/
│   │   └── emails/
│   │       └── 2024/...
│   └── work@company.com/
│       └── emails/
│           └── 2024/...
```

### Config Structure

```yaml
archive_dir: /Volumes/Secure/ownmail

# Provider defaults
providers:
  gmail:
    include_labels: true
  imap:
    # Common IMAP defaults

# Accounts
accounts:
  - provider: gmail
    address: alice@gmail.com

  - provider: imap
    address: me@fastmail.com
    imap_server: imap.fastmail.com
    imap_port: 993
    # Password stored in keychain

  - provider: imap
    address: work@company.com
    imap_server: imap.company.com
    imap_port: 993
```

### Keychain Structure

All credentials under service `ownmail`:

| Account Key | Description |
|-------------|-------------|
| `client-credentials/gmail` | OAuth client ID (shared for all Gmail accounts) |
| `oauth-token/alice@gmail.com` | OAuth refresh token (per account) |
| `imap-password/me@fastmail.com` | IMAP password or app-specific password |

### CLI Changes

```bash
# Backup all accounts
ownmail backup

# Backup specific account
ownmail backup --account alice@gmail.com

# Search across all accounts
ownmail search "invoice"

# Search specific account
ownmail search "invoice" --account alice@gmail.com

# Account management
ownmail accounts list
ownmail accounts add
ownmail accounts remove alice@gmail.com
```

### Database Schema

```sql
-- Add account column to emails table
ALTER TABLE emails ADD COLUMN account TEXT;

-- Update sync_state for per-account tracking
-- Key format: "<account>/<key>" e.g. "alice@gmail.com/history_id"
```

### Provider Architecture

```python
# providers/base.py
class EmailProvider(ABC):
    account: str  # e.g. "alice@gmail.com"

    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_new_message_ids(self) -> List[str]: ...

    @abstractmethod
    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
        """Returns (raw_email, labels)"""
        ...

# providers/gmail.py
class GmailProvider(EmailProvider): ...

# providers/imap.py
class IMAPProvider(EmailProvider): ...
```

### Implementation Plan

1. **Refactor**: Extract provider interface from current Gmail code
2. **IMAP Provider**: Implement generic IMAP support
3. **Multi-account**: Add account column, update CLI
4. **Config**: New config format with accounts list
5. **Migration**: Script to move existing emails to new structure

---

## v0.3.0 — Outlook/Microsoft 365 Support

**Goal**: Add Outlook support via Microsoft Graph API.

### Microsoft Graph API

- Uses OAuth2 (similar to Gmail)
- Requires Azure AD app registration
- Folders instead of labels (Inbox, Sent, custom folders)

### Config

```yaml
accounts:
  - provider: outlook
    address: bob@outlook.com
    include_folders: true  # Store folder info like labels

providers:
  outlook:
    include_folders: true
```

### Keychain

| Account Key | Description |
|-------------|-------------|
| `client-credentials/outlook` | Azure AD app client ID/secret |
| `oauth-token/bob@outlook.com` | OAuth refresh token |

### Implementation

1. Create `providers/outlook.py` using `msal` library
2. Add folder → X-Outlook-Folders header mapping
3. Handle Outlook-specific quirks (conversation threading, etc.)

---

## v0.4.0 — Web UI

**Goal**: Self-hosted web interface to browse and search your email archive.

### Features

- [ ] Email list view with search
- [ ] Email detail view (HTML rendering)
- [ ] Attachment download
- [ ] Label/folder filtering
- [ ] Mobile-responsive design
- [ ] Dark mode

### Tech Stack Options

| Option | Pros | Cons |
|--------|------|------|
| **Flask + Jinja** | Simple, Python-only | Basic UI |
| **FastAPI + Vue/React** | Modern, API-first | More complex |
| **Textual (TUI)** | Terminal-based, no browser | Limited formatting |

### Architecture

```
ownmail/
├── cli.py           # CLI commands
├── core/            # Shared logic
├── providers/       # Email providers
└── web/
    ├── app.py       # FastAPI/Flask app
    ├── templates/   # HTML templates
    └── static/      # CSS/JS
```

### Running

```bash
# Start web server
ownmail web --port 8080

# Access at http://localhost:8080
```

### Security Considerations

- Local-only by default (bind to 127.0.0.1)
- Optional authentication for LAN access
- Read-only (no email sending/deletion)
- HTTPS support for remote access

---

## Backlog

Items not yet scheduled:

### Headless Server Support

Encrypted file fallback for servers without a desktop keyring.

### Email Export

```bash
# Export to mbox format
ownmail export --format mbox --output backup.mbox

# Export to PDF
ownmail export --format pdf --query "from:important@example.com"
```

### Deduplication

Detect and handle duplicate emails (same Message-ID across accounts).

### Scheduled Backups

```bash
# Generate launchd/cron config
ownmail schedule --interval daily
```

### Encryption at Rest

For users who can't use an encrypted volume, encrypt both emails and database.

**Config:**

```yaml
encrypt_at_rest: true  # Default: false
# Encryption key stored in system keychain under "ownmail/encryption-key"
```

Note: This setting only applies to **future downloads** and new database files. Use `ownmail encrypt` to convert an existing archive. The program handles mixed encrypted/unencrypted emails transparently (detects per-file).

**Scope:**

| Component | Encryption Method |
|-----------|------------------|
| `.eml` files | AES-256-GCM per file |
| `ownmail.db` | Decrypt on startup → temp file → re-encrypt on exit |

**Commands:**

```bash
# Convert existing archive to encrypted
ownmail encrypt

# Convert back to unencrypted
ownmail decrypt
```

**Considerations:**

- ~200-600ms startup/shutdown overhead for database (acceptable for <200MB)
- Existing commands (verify, rehash, reindex, search) work transparently
- Crash recovery: cleanup decrypted temp files on next startup
- Key rotation: future enhancement

**Alternative:** Use an encrypted volume (macOS APFS, Linux LUKS, Windows BitLocker) — simpler and already recommended.

### Statistics & Analytics

```bash
ownmail stats --detailed
# Top senders, emails per month, attachment sizes, etc.
```

### Optional Attachment Download

Config option to skip downloading attachments for smaller backups:

```yaml
include_attachments: false  # Default: true
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
