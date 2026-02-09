# v0.2.0 Implementation Plan

## Overview

Refactor ownmail to support multiple email accounts from different providers (Gmail, IMAP).

## Current Architecture

```
ownmail.py (single file, ~2150 lines)
├── load_config()
├── KeychainStorage          # Credential storage
├── ArchiveDatabase          # SQLite + FTS5
├── EmailParser              # Parse .eml files
├── GmailArchive             # Main class (mixed concerns)
│   ├── authenticate()
│   ├── get_new_message_ids()
│   ├── download_message()
│   ├── index_email()
│   ├── cmd_backup()
│   ├── cmd_search()
│   ├── cmd_reindex()
│   └── ... (all CLI commands)
└── main()
```

**Problems:**
1. `GmailArchive` mixes provider-specific logic with generic archive operations
2. No abstraction layer for different providers
3. Keychain stores credentials for single account
4. Database doesn't track which account owns each email
5. All emails go to same `emails/` directory

## Target Architecture

```
ownmail/
├── __init__.py
├── __main__.py              # Entry point
├── cli.py                   # CLI commands (argparse)
├── config.py                # Config loading/validation
├── database.py              # ArchiveDatabase (with account support)
├── keychain.py              # KeychainStorage (multi-account)
├── parser.py                # EmailParser
├── archive.py               # EmailArchive (orchestrator)
└── providers/
    ├── __init__.py
    ├── base.py              # EmailProvider ABC
    ├── gmail.py             # GmailProvider
    └── imap.py              # IMAPProvider
```

## Phase 1: Extract Provider Interface (No Multi-Account Yet)

**Goal:** Split `GmailArchive` into provider + archive without changing behavior.

### Step 1.1: Create package structure
- Create `ownmail/` directory
- Move code into modules
- Keep `ownmail.py` as thin wrapper for backward compatibility

### Step 1.2: Define EmailProvider ABC
```python
# ownmail/providers/base.py
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'gmail', 'imap')."""
        ...
    
    @property
    @abstractmethod
    def account(self) -> str:
        """Account identifier (email address)."""
        ...
    
    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the provider."""
        ...
    
    @abstractmethod
    def get_new_message_ids(self, downloaded_ids: set) -> List[str]:
        """Get IDs of messages not yet downloaded."""
        ...
    
    @abstractmethod
    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
        """Download a message. Returns (raw_email_bytes, labels)."""
        ...
    
    @abstractmethod
    def get_sync_state(self) -> Optional[str]:
        """Get provider-specific sync state (e.g., Gmail history_id)."""
        ...
    
    @abstractmethod
    def set_sync_state(self, state: str) -> None:
        """Save provider-specific sync state."""
        ...
```

### Step 1.3: Extract GmailProvider
Move Gmail-specific code from `GmailArchive` to `GmailProvider`:
- `authenticate()` → uses OAuth2 flow
- `get_new_message_ids()` → uses Gmail History API
- `_get_all_message_ids()` → lists all messages
- `_get_messages_since_history()` → incremental sync
- `_get_labels_for_message()` → Gmail labels
- `_inject_labels()` → add X-Gmail-Labels header
- `download_message()` → fetch raw message

### Step 1.4: Create EmailArchive (Orchestrator)
Generic archive operations that work with any provider:
- `backup()` → calls provider methods, saves to disk
- `index_email()` → unchanged
- `search()` → unchanged  
- `verify()` → unchanged
- etc.

### Step 1.5: Update CLI
- Update `main()` to use new structure
- Keep same CLI interface

### Step 1.6: Tests
- Ensure all existing tests pass
- Add provider abstraction tests

---

## Phase 2: Implement IMAP Provider

### Step 2.1: IMAPProvider basics
```python
# ownmail/providers/imap.py
import imaplib
import email

class IMAPProvider(EmailProvider):
    def __init__(self, account: str, server: str, port: int = 993):
        self._account = account
        self.server = server
        self.port = port
        self.conn: Optional[imaplib.IMAP4_SSL] = None
    
    @property
    def name(self) -> str:
        return "imap"
    
    @property
    def account(self) -> str:
        return self._account
    
    def authenticate(self) -> None:
        password = keychain.get_password(f"imap-password/{self._account}")
        self.conn = imaplib.IMAP4_SSL(self.server, self.port)
        self.conn.login(self._account, password)
    
    def get_new_message_ids(self, downloaded_ids: set) -> List[str]:
        # IMAP UIDs are folder-specific, so we use Message-ID header
        # or construct unique ID from folder+UID
        ...
    
    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
        # Fetch raw message, return folder as "label"
        ...
```

### Step 2.2: IMAP Message IDs
Challenge: IMAP UIDs are folder-specific, not globally unique.

Options:
1. **Use Message-ID header** — Standard but can be missing/duplicated
2. **Use folder/UID composite** — e.g., `INBOX/12345` — unique but changes if message moves
3. **Hash of Message-ID + Date + From** — More robust

Decision: Use `<folder>/<UID>` for internal tracking, but also store Message-ID header for dedup.

### Step 2.3: IMAP Folder Mapping
- Map IMAP folders to "labels" similar to Gmail
- Store in `X-IMAP-Folders` header

### Step 2.4: IMAP Incremental Sync
- Store highest UID per folder in sync_state
- On next sync, fetch UIDs > stored UID
- Handle UIDVALIDITY changes (folder reset)

### Step 2.5: IMAP Setup Command
```bash
ownmail accounts add --provider imap
# Prompts for: email, server, port
# Stores password in keychain
```

---

## Phase 3: Multi-Account Support

### Step 3.1: Database Schema Changes
```sql
-- Add account column
ALTER TABLE emails ADD COLUMN account TEXT;

-- Index for per-account queries
CREATE INDEX idx_emails_account ON emails(account);

-- Sync state becomes per-account
-- Key format: "<account>/<key>"
-- e.g., "alice@gmail.com/history_id"
```

### Step 3.2: Directory Structure
```
archive_dir/
├── ownmail.db
├── accounts/
│   ├── alice@gmail.com/
│   │   └── emails/
│   │       └── 2024/...
│   └── me@fastmail.com/
│       └── emails/
│           └── 2024/...
```

### Step 3.3: Config Structure
```yaml
archive_dir: /Volumes/Secure/ownmail

providers:
  gmail:
    include_labels: true
  imap:
    # defaults

accounts:
  - provider: gmail
    address: alice@gmail.com

  - provider: imap
    address: me@fastmail.com
    imap_server: imap.fastmail.com
    imap_port: 993
```

### Step 3.4: Keychain Structure
Service: `ownmail`
Account keys:
- `client-credentials/gmail` — OAuth client ID (shared)
- `oauth-token/alice@gmail.com` — per Gmail account
- `imap-password/me@fastmail.com` — per IMAP account

### Step 3.5: CLI Changes
```bash
# Account management
ownmail accounts list
ownmail accounts add [--provider gmail|imap]
ownmail accounts remove <email>

# Backup with account filter
ownmail backup                      # All accounts
ownmail backup --account alice@gmail.com

# Search with account filter
ownmail search "query"              # All accounts
ownmail search "query" --account alice@gmail.com
```

### Step 3.6: Migration Script
For existing single-account archives:
1. Detect old structure (emails/ in root)
2. Prompt for account email
3. Move to accounts/<email>/emails/
4. Update database with account column

---

## Implementation Order

### Sprint 1: Provider Abstraction
- [ ] Create package structure
- [ ] Define EmailProvider ABC
- [ ] Extract GmailProvider
- [ ] Create EmailArchive orchestrator
- [ ] Update CLI to use new structure
- [ ] Verify all tests pass

### Sprint 2: IMAP Provider
- [ ] Implement IMAPProvider
- [ ] Add IMAP setup flow (accounts add)
- [ ] Test with common providers (Fastmail, Gmail IMAP, etc.)
- [ ] Handle edge cases (UIDVALIDITY, missing Message-ID)

### Sprint 3: Multi-Account
- [ ] Update database schema
- [ ] Implement per-account directories
- [ ] Update config format
- [ ] Update keychain structure
- [ ] Add accounts commands
- [ ] Add --account flag to commands
- [ ] Create migration script

---

## Open Questions

1. **Single file vs package?**
   - Package is cleaner but more complex distribution
   - Decision: Package, with `python -m ownmail` support

2. **IMAP message ID strategy?**
   - Decision: `<folder>/<UID>` with UIDVALIDITY tracking

3. **Default account?**
   - If only one account, use it automatically
   - If multiple, require --account or backup all

4. **Backward compatibility?**
   - Keep `ownmail.py` wrapper for transition
   - Eventually deprecate in favor of `python -m ownmail`

---

## Files to Create/Modify

### New Files
- `ownmail/__init__.py`
- `ownmail/__main__.py`
- `ownmail/cli.py`
- `ownmail/config.py`
- `ownmail/database.py`
- `ownmail/keychain.py`
- `ownmail/parser.py`
- `ownmail/archive.py`
- `ownmail/providers/__init__.py`
- `ownmail/providers/base.py`
- `ownmail/providers/gmail.py`
- `ownmail/providers/imap.py`

### Modified Files
- `ownmail.py` — thin wrapper importing from package
- `pyproject.toml` — update entry points
- `tests/` — update imports

---

## Risk Mitigation

1. **Breaking changes**: Keep CLI interface identical
2. **Data loss**: Never modify/delete .eml files
3. **Test coverage**: Run full test suite after each phase
4. **Incremental**: Each phase should be deployable independently
