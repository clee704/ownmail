# ownmail Roadmap

## Vision

**ownmail** is a file-first email backup tool. Your emails are stored as standard `.eml` files that you own and control. The database is just an index — the files are the source of truth.

---

## Next Up — Web UI Polish

**Goal**: Finish and harden the web interface.

The web UI is functional (Flask + Jinja, search, email detail, attachment download, dark mode, image blocking, pagination). Settings page with runtime configuration, trusted senders, and image blocking are implemented. Remaining work:

### Features

- [ ] Label sidebar: show all labels in a left sidebar with email counts; support lexicographic or custom sort order (via config)
- [ ] Simple password-based authentication for LAN/tunnel access (single shared password, session cookie after login)
- [ ] Verify CJK attachment filename encoding (RFC 5987) — check if this is still an issue

---

## Backlog

Items not yet scheduled:

### Import & Scan

~~Support importing externally-sourced `.eml` files (e.g. Tuta, Thunderbird exports) into the archive.~~ Implemented: `ownmail import <path> [--account EMAIL] [--move] [--dry-run]` and `ownmail scan [--account EMAIL] [--dry-run]`. See `archive.py`'s `import_email()`/`import_path()`/`scan_archive()` and `commands.py`'s `cmd_import()`/`cmd_scan()`.

### Email Export

```bash
ownmail export --format mbox --output backup.mbox
ownmail export --format pdf --query "from:important@example.com"
```

### Deduplication

~~Detect duplicate emails across accounts/imports (same `content_hash`). `ownmail dedup` command.~~ Cross-folder dedup within IMAP is handled by the IMAP provider. Content-hash dedup during download skips duplicate emails. `verify --fix` detects and cleans up duplicates in the archive. A standalone `ownmail dedup` command may be added later if needed.

### Headless Server Support

Encrypted file fallback for servers without a desktop keyring.

### Encryption at Rest

Encrypt `.eml` files (AES-256-GCM per file) and database. `ownmail encrypt` / `ownmail decrypt` commands. Key in system keychain. Mixed encrypted/unencrypted handled transparently. Alternative: use OS-level encrypted volumes (APFS, LUKS, BitLocker).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
