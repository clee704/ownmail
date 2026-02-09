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

---

## v0.2.0 — Multiple Accounts

**Goal**: Support backing up multiple email accounts to the same archive.

### Directory Structure

```
/Volumes/Secure/ownmail/
├── ownmail.db                    # Global index (all accounts)
├── accounts/
│   ├── alice@gmail.com/
│   │   └── emails/
│   │       └── 2024/...
│   ├── bob@gmail.com/
│   │   └── emails/
│   │       └── 2024/...
│   └── work@company.com/
│       └── emails/
│           └── 2024/...
```

### Config Structure (v0.2)

```yaml
# Global settings
archive_dir: /Volumes/Secure/ownmail

# Provider defaults
providers:
  gmail:
    include_labels: true

# Accounts
accounts:
  - provider: gmail
    address: alice@gmail.com
    # inherits include_labels: true from provider defaults

  - provider: gmail
    address: work@company.com
    include_labels: false  # override provider default
```

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

# List configured accounts
ownmail accounts list

# Add new account
ownmail accounts add
```

### Database Schema

```sql
-- Add account column to emails table
ALTER TABLE emails ADD COLUMN account TEXT;

-- Index for per-account queries
CREATE INDEX idx_emails_account ON emails(account);
```

---

## v0.3.0 — Additional Email Providers

**Goal**: Support email services beyond Gmail.

### Providers to Support

| Provider | Protocol | Priority | Notes |
|----------|----------|----------|-------|
| Gmail | OAuth2 + REST API | ✅ Done | |
| Outlook/M365 | OAuth2 + MS Graph | High | Large user base |
| Generic IMAP | IMAP + App Password | High | Covers most providers |
| iCloud Mail | IMAP + App Password | Medium | Requires app-specific password |
| Fastmail | JMAP | Medium | Modern protocol |
| ProtonMail | Proton Bridge | Low | Requires local bridge |
| Tutanota | — | Low | No IMAP, would need their API |

### Architecture

```python
# providers/base.py
class EmailProvider(ABC):
    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_message_ids(self) -> List[str]: ...

    @abstractmethod
    def download_message(self, msg_id: str) -> bytes: ...

    @abstractmethod
    def get_labels(self, msg_id: str) -> List[str]: ...

# providers/gmail.py
class GmailProvider(EmailProvider): ...

# providers/outlook.py
class OutlookProvider(EmailProvider): ...

# providers/imap.py
class IMAPProvider(EmailProvider): ...
```

### Config with Multiple Providers

```yaml
archive_dir: /Volumes/Secure/ownmail

providers:
  gmail:
    include_labels: true
  outlook:
    include_categories: true
  imap:
    # IMAP-specific defaults

accounts:
  - provider: gmail
    address: alice@gmail.com

  - provider: outlook
    address: bob@outlook.com
    include_labels: false  # override provider default

  - provider: imap
    address: me@example.com
    imap_server: imap.example.com
    imap_port: 993
    # Credentials stored in keychain under "ownmail/me@example.com"
```

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
