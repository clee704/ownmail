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
2. For each file: parse, generate `provider_id` (`local:{Message-ID}` or `local:sha256:{content_hash}`), derive `email_id` via `make_email_id(account, provider_id)`, check for duplicates, copy/move to archive, register + index in database.
3. Batch-commit every 10 emails. Support Ctrl-C with graceful resume.

#### `ownmail scan [--account EMAIL] [--dry-run]`

Detect `.eml` files already present in the archive directory that aren't tracked in the database (e.g., manually placed there). Register and index them in-place — no file moving.

### Provider ID strategy

- Use `Message-ID` header as `provider_id`: `local:<Message-ID>`.
- If missing, fall back to content hash: `local:sha256:{hash}`.
- `local:` prefix avoids collisions with Gmail/IMAP provider IDs.
- `email_id` (PK) is derived as usual: `sha256(f"{account}/{provider_id}").hexdigest()[:24]`.

### Code changes

- `database.py`: Add `get_tracked_filenames(account=None) -> set[str]`. No schema changes needed.
- `archive.py`: Extract file-saving logic into reusable helper. Add `import_email()` and `scan_archive()` methods.
- `cli.py`: Add `import` and `scan` subcommands.
- `commands.py`: Add `cmd_import()` and `cmd_scan()` with progress display and Ctrl-C handling.

---

## Next Up — Web UI Polish

**Goal**: Finish and harden the web interface.

The web UI is functional (Flask + Jinja, search, email detail, attachment download, dark mode, image blocking, pagination). Remaining work:

### Features

- [ ] Label sidebar: show all labels in a left sidebar with email counts; support lexicographic or custom sort order (via config)
- [ ] Simple password-based authentication for LAN/tunnel access (single shared password, session cookie after login)
- [ ] Verify CJK attachment filename encoding (RFC 5987) — check if this is still an issue

---

## Backlog

Items not yet scheduled:

### Email Export

```bash
ownmail export --format mbox --output backup.mbox
ownmail export --format pdf --query "from:important@example.com"
```

### Deduplication

Detect duplicate emails across accounts/imports (same `content_hash`). `ownmail dedup` command. Cross-folder dedup within IMAP is already handled by the IMAP provider.

### Headless Server Support

Encrypted file fallback for servers without a desktop keyring.

### Encryption at Rest

Encrypt `.eml` files (AES-256-GCM per file) and database. `ownmail encrypt` / `ownmail decrypt` commands. Key in system keychain. Mixed encrypted/unencrypted handled transparently. Alternative: use OS-level encrypted volumes (APFS, LUKS, BitLocker).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
