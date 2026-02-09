# ownmail Roadmap

## Vision

**ownmail** is a file-first email backup tool. Your emails are stored as standard `.eml` files that you own and control. The database is just an index — the files are the source of truth.

---

## Next Up — Import & Scan

**Goal**: Support importing externally-sourced `.eml` files into the archive.

Currently, only emails downloaded by the `backup` command are recognized. This means exports from Tuta, Thunderbird, or any other client can't be added to the archive. Since ownmail's philosophy is "files as source of truth," any `.eml` file should be a first-class citizen.

### Commands

#### `ownmail import <path> [--account EMAIL] [--move] [--dry-run]`

Import `.eml` files (or directories of them) into the archive. Files are copied into the standard directory structure, registered in the database, and indexed for search.

- `<path>` — File or directory (recursive).
- `--account EMAIL` — Associate with this account. Defaults to the `From` header address.
- `--move` — Move files instead of copying (delete originals after successful import).
- `--dry-run` — Show what would be imported without doing it.

**Behavior:**
1. Scan path for `.eml` files.
2. For each file: parse, generate message ID (`local:{Message-ID}` or `local:sha256:{hash}`), check for duplicates, copy/move to archive, register + index in database.
3. Batch-commit every 10 emails. Support Ctrl-C with graceful resume.

#### `ownmail scan [--account EMAIL] [--dry-run]`

Detect `.eml` files already present in the archive directory that aren't tracked in the database (e.g., manually placed there). Register and index them in-place — no file moving.

### Message ID strategy

- Use `Message-ID` header: `local:<Message-ID>`.
- If missing, fall back to SHA256: `local:sha256:{hash}`.
- Prefix avoids collisions with provider-native IDs.

### Code changes

- `database.py`: Add `get_tracked_filenames(account=None) -> set[str]`. No schema changes needed.
- `archive.py`: Extract file-saving logic into reusable helper. Add `import_email()` and `scan_archive()` methods.
- `cli.py`: Add `import` and `scan` subcommands.
- `commands.py`: Add `cmd_import()` and `cmd_scan()` with progress display and Ctrl-C handling.

---

## Next Up — IMAP Provider

**Goal**: Support generic IMAP email backup. Covers Fastmail, company mail servers, self-hosted, etc.

The config system already validates `type: imap` sources, and `keychain.py` has `save_imap_password()`/`load_imap_password()` ready.

### Design

- Connect via `IMAP4_SSL`, credentials from keychain (`imap-password/{email}`).
- **Folder scanning with deduplication**: List all folders, scan each for UIDs + `Message-ID` headers. Same `Message-ID` across multiple folders → download once, store all folder names as labels.
- **Labels**: Store IMAP folder names in the `labels` column, unified with Gmail labels. Searchable via `label:`.
- **Incremental sync**: UID-based. Store highest UID per folder in `sync_state`. Detect `UIDVALIDITY` changes for full resync.
- **Folder filtering**: Optional `exclude_folders` config (Trash, Spam, Drafts).

### Config

```yaml
sources:
  - name: work_imap
    type: imap
    host: imap.company.com
    account: user@company.com
    auth:
      secret_ref: keychain:imap-password/user@company.com
    exclude_folders:  # optional
      - Trash
      - Spam
```

---

## Next Up — Retry Logic for Transient Failures

**Goal**: Make backup resilient to transient API errors instead of crashing.

### Current gaps

- HTTP 503 (service unavailable) propagates as an unhandled crash.
- Individual message failures within a batch are skipped but not retried.
- No `try/except` around `download_messages_batch()` in `archive.py` — a single bad batch aborts the entire backup.
- Failed message IDs are not tracked (only an aggregate `error_count`).

### Plan

1. **Retry individual failures in `gmail.py`**: After a batch completes, retry failed messages individually with exponential backoff. Add `_is_retriable()` helper for 429, 503, timeout, connection reset.
2. **Wrap batch calls in `archive.py`**: Catch exceptions from `download_messages_batch()` so one bad batch doesn't abort everything.
3. **Track failed IDs**: Return `failed_ids` list from `backup()` with error reasons. Print summary at the end.
4. **Add 503 to batch-level retry**: Currently only 429 triggers batch retry.

---

## Next Up — Web UI Polish

**Goal**: Finish and harden the web interface.

The web UI is functional (Flask + Jinja, search, email detail, attachment download, dark mode, image blocking, pagination). Remaining work:

### Improvements

- [x] Replace iframe with inline HTML rendering (sanitized) — iframe has sizing issues (infinite growth, incorrect height), waits for load before resizing (clunky scroll), and makes styling difficult
- [x] Color nested quote text to match quote bar color at each nesting level (like Gmail)
- [x] Rework image/content blocking UX: show a dismissible prompt for untrusted senders; move "load/block content" and "trust/untrust sender" actions into `...` overflow menu; fix prompt styling for dark mode

### Features

- [ ] Label sidebar: show all labels in a left sidebar with email counts; support lexicographic or custom sort order (via config)
- [ ] Simple password-based authentication for LAN/tunnel access (single shared password, session cookie after login)
- [ ] Verify CJK attachment filename encoding (RFC 5987) — check if this is still an issue

---

## Later — Outlook / Microsoft 365

**Goal**: Add Outlook support via Microsoft Graph API.

- OAuth2 via Azure AD app registration.
- Folders instead of labels (mapped to `X-Outlook-Folders` header).
- Create `providers/outlook.py` using `msal` library.
- Handle Outlook-specific quirks (conversation threading, etc.).

---

## Later — Parser Refactoring

**Goal**: Improve readability of `parser.py` (~670 LOC) without changing behavior.

The parser works correctly but has deep nesting and long function bodies. Every fallback path exists for a real-world encoding edge case (especially Korean EUC-KR/CP949).

- Extract charset detection into `_detect_charset(raw_bytes, declared_charset=None) -> str`.
- Extract RFC 2047 grouped-part decoding into `_decode_grouped_rfc2047_parts()`.
- Compile regex patterns at module level (some are compiled inline on every call).
- Keep the public API (`parse_file()`, `parse_raw()`) unchanged.

---

## Backlog

Items not yet scheduled:

### Email Export

```bash
ownmail export --format mbox --output backup.mbox
ownmail export --format pdf --query "from:important@example.com"
```

### Deduplication

Detect duplicate emails (same `Message-ID` across accounts/imports). `ownmail dedup` command comparing `content_hash`.

### Scheduled Backups

```bash
ownmail schedule --interval daily  # Generate launchd/cron config
```

### Headless Server Support

Encrypted file fallback for servers without a desktop keyring.

### Encryption at Rest

Encrypt `.eml` files (AES-256-GCM per file) and database. `ownmail encrypt` / `ownmail decrypt` commands. Key in system keychain. Mixed encrypted/unencrypted handled transparently. Alternative: use OS-level encrypted volumes (APFS, LUKS, BitLocker).

### Statistics & Analytics

```bash
ownmail stats --detailed  # Top senders, emails per month, attachment sizes
```

### Optional Attachment Download

```yaml
include_attachments: false  # Default: true
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
