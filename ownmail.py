#!/usr/bin/env python3
"""
ownmail - Own your mail.

A file-based email backup and search tool. Your emails, your files, your drive.
All credentials are stored securely in macOS Keychain.

Commands:
    setup      - Configure OAuth credentials (one-time setup)
    backup     - Download new emails
    search     - Full-text search across downloaded emails
    stats      - Show archive statistics
    reindex    - Rebuild the search index
    add-labels - Add Gmail labels to existing emails
    verify     - Verify integrity of downloaded emails
    rehash     - Compute hashes for emails without them
    sync-check - Compare local archive with server

Usage:
    ownmail setup
    ownmail backup [--archive-dir PATH]
    ownmail search "query" [--archive-dir PATH]
    ownmail stats
"""

import argparse
import base64
import email
import hashlib
import json
import os
import re
import signal
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from email.policy import default as email_policy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional YAML support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Third-party imports
try:
    import keyring
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError as e:
    print(f"Missing required package: {e}")
    print("\nPlease install required packages:")
    print("    pip install ownmail")
    sys.exit(1)

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
DEFAULT_ARCHIVE_DIR = SCRIPT_DIR / "archive"
DEFAULT_CONFIG_FILENAME = "config.yaml"
KEYCHAIN_SERVICE = "ownmail"
KEYCHAIN_ACCOUNT_TOKEN = "oauth-token"
KEYCHAIN_ACCOUNT_CREDENTIALS = "client-credentials"

# Gmail API scopes - readonly access to emails
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Search order:
    1. Explicit --config path
    2. ./config.yaml (current working directory)
    3. Script directory config.yaml
    """
    search_paths = []

    if config_path:
        search_paths.append(config_path)
    else:
        # Check current working directory first
        search_paths.append(Path.cwd() / DEFAULT_CONFIG_FILENAME)
        # Then script directory
        search_paths.append(SCRIPT_DIR / DEFAULT_CONFIG_FILENAME)

    for path in search_paths:
        if path.exists():
            if not HAS_YAML:
                print(f"Found config file {path} but PyYAML is not installed.")
                print("Install with: pip install pyyaml")
                print("Continuing without config file...\n")
                return {}

            with open(path) as f:
                config = yaml.safe_load(f) or {}
                print(f"Loaded config from: {path}")
                return config

    return {}


class KeychainStorage:
    """Securely store secrets in macOS Keychain."""

    def __init__(self, service: str):
        self.service = service

    def save_client_credentials(self, credentials_json: str) -> None:
        """Save OAuth client credentials to Keychain."""
        # Validate JSON before saving
        try:
            data = json.loads(credentials_json)
            if "installed" not in data and "web" not in data:
                raise ValueError("Invalid credentials format")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        keyring.set_password(self.service, KEYCHAIN_ACCOUNT_CREDENTIALS, credentials_json)

    def load_client_credentials(self) -> Optional[str]:
        """Load OAuth client credentials from Keychain."""
        return keyring.get_password(self.service, KEYCHAIN_ACCOUNT_CREDENTIALS)

    def has_client_credentials(self) -> bool:
        """Check if client credentials are stored."""
        return self.load_client_credentials() is not None

    def delete_client_credentials(self) -> None:
        """Delete client credentials from Keychain."""
        try:
            keyring.delete_password(self.service, KEYCHAIN_ACCOUNT_CREDENTIALS)
        except keyring.errors.PasswordDeleteError:
            pass

    def save_token(self, creds: Credentials) -> None:
        """Save OAuth token to Keychain."""
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [],
        }
        keyring.set_password(self.service, KEYCHAIN_ACCOUNT_TOKEN, json.dumps(token_data))
        print("✓ OAuth token saved to macOS Keychain")

    def load_token(self) -> Optional[Credentials]:
        """Load OAuth token from Keychain."""
        token_json = keyring.get_password(self.service, KEYCHAIN_ACCOUNT_TOKEN)
        if not token_json:
            return None

        try:
            token_data = json.loads(token_json)
            creds = Credentials(
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                token_uri=token_data["token_uri"],
                client_id=token_data["client_id"],
                client_secret=token_data["client_secret"],
                scopes=token_data["scopes"],
            )
            return creds
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse stored token: {e}")
            return None

    def delete_token(self) -> None:
        """Delete OAuth token from Keychain."""
        try:
            keyring.delete_password(self.service, KEYCHAIN_ACCOUNT_TOKEN)
        except keyring.errors.PasswordDeleteError:
            pass


class ArchiveDatabase:
    """SQLite database for tracking emails and full-text search."""

    def __init__(self, archive_dir: Path):
        self.archive_dir = archive_dir
        self.db_path = archive_dir / "ownmail.db"
        archive_dir.mkdir(parents=True, exist_ok=True)

        is_new_db = not self.db_path.exists()
        if is_new_db:
            print(f"Creating new database: {self.db_path}")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Main emails table - minimal metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    message_id TEXT PRIMARY KEY,
                    filename TEXT,
                    downloaded_at TEXT,
                    content_hash TEXT,
                    indexed_hash TEXT
                )
            """)

            # Sync state for incremental backup
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Full-text search index using FTS5
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
                    message_id,
                    subject,
                    sender,
                    recipients,
                    date_str,
                    body,
                    attachments,
                    tokenize='porter unicode61'
                )
            """)

            conn.commit()

    def get_history_id(self) -> Optional[str]:
        """Get the last synced history ID for incremental sync."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT value FROM sync_state WHERE key = 'history_id'"
            ).fetchone()
            return result[0] if result else None

    def set_history_id(self, history_id: str) -> None:
        """Save the current history ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('history_id', ?)",
                (history_id,),
            )
            conn.commit()

    def is_downloaded(self, message_id: str) -> bool:
        """Check if a message has already been downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM emails WHERE message_id = ?", (message_id,)
            ).fetchone()
            return result is not None

    def get_downloaded_ids(self) -> set:
        """Get all downloaded message IDs."""
        with sqlite3.connect(self.db_path) as conn:
            results = conn.execute("SELECT message_id FROM emails").fetchall()
            return {row[0] for row in results}

    def mark_downloaded(self, message_id: str, filename: str, content_hash: str = None, conn: sqlite3.Connection = None) -> None:
        """Mark a message as downloaded.

        Args:
            conn: Optional existing connection (for batching). If None, creates one and commits.
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO emails
                (message_id, filename, downloaded_at, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (message_id, filename, datetime.now().isoformat(), content_hash),
            )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def index_email(
        self,
        message_id: str,
        subject: str,
        sender: str,
        recipients: str,
        date_str: str,
        body: str,
        attachments: str,
        conn: sqlite3.Connection = None,
        skip_delete: bool = False,
    ) -> None:
        """Add email to full-text search index.

        Args:
            conn: Optional existing connection (for batching). If None, creates one and commits.
            skip_delete: If True, skip the DELETE (for new emails that aren't in the index yet).
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        try:
            # Remove existing entry if any (skip for new emails - DELETE is slow on FTS)
            if not skip_delete:
                conn.execute("DELETE FROM emails_fts WHERE message_id = ?", (message_id,))
            # Insert new entry
            conn.execute(
                """
                INSERT INTO emails_fts
                (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, subject, sender, recipients, date_str, body, attachments),
            )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def is_indexed(self, message_id: str) -> bool:
        """Check if a message is in the search index."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM emails_fts WHERE message_id = ?", (message_id,)
            ).fetchone()
            return result is not None

    def search(self, query: str, limit: int = 50) -> List[Tuple]:
        """Search emails using FTS5."""
        with sqlite3.connect(self.db_path) as conn:
            # Use FTS5 MATCH syntax
            # Support field-specific queries like from:, subject:, etc.
            fts_query = self._convert_query(query)

            results = conn.execute(
                """
                SELECT
                    e.message_id,
                    e.filename,
                    f.subject,
                    f.sender,
                    f.date_str,
                    snippet(emails_fts, 5, '>>>', '<<<', '...', 32) as snippet
                FROM emails_fts f
                JOIN emails e ON e.message_id = f.message_id
                WHERE emails_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            return results

    def _convert_query(self, query: str) -> str:
        """Convert user query to FTS5 syntax."""
        # Map common email search operators to FTS5 column names
        query = re.sub(r'\bfrom:', 'sender:', query)
        query = re.sub(r'\bto:', 'recipients:', query)
        query = re.sub(r'\battachment:', 'attachments:', query)
        return query

    def get_stats(self) -> dict:
        """Get archive statistics."""
        with sqlite3.connect(self.db_path) as conn:
            email_count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            indexed_count = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]

            # Get date range
            oldest = conn.execute(
                "SELECT MIN(downloaded_at) FROM emails"
            ).fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(downloaded_at) FROM emails"
            ).fetchone()[0]

            return {
                "total_emails": email_count,
                "indexed_emails": indexed_count,
                "oldest_backup": oldest,
                "newest_backup": newest,
            }

    def clear_index(self) -> None:
        """Clear the full-text search index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM emails_fts")
            conn.commit()


class EmailParser:
    """Parse .eml files for indexing. Handles malformed emails gracefully."""

    @staticmethod
    def _sanitize_header(value: str) -> str:
        """Remove CR/LF and other problematic chars from header values."""
        if not value:
            return ""
        # Replace CR/LF with space, collapse multiple spaces
        result = value.replace("\r", " ").replace("\n", " ")
        result = re.sub(r'\s+', ' ', result)
        return result.strip()

    @staticmethod
    def _safe_get_header(msg, header_name: str) -> str:
        """Safely extract a header, handling encoding errors."""
        try:
            val = msg.get(header_name, "") or ""
            return EmailParser._sanitize_header(str(val))
        except Exception:
            # If header parsing fails completely, try raw access
            try:
                val = msg.get(header_name, defects=[]) or ""
                return EmailParser._sanitize_header(str(val))
            except Exception:
                return ""

    @staticmethod
    def _safe_get_content(part) -> str:
        """Safely extract content from a message part."""
        try:
            payload = part.get_content()
            if isinstance(payload, str):
                return payload
            elif isinstance(payload, bytes):
                # Try common encodings
                for encoding in ['utf-8', 'euc-kr', 'cp949', 'iso-8859-1']:
                    try:
                        return payload.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return payload.decode('utf-8', errors='replace')
        except Exception:
            # Last resort: try get_payload
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode('utf-8', errors='replace')
            except Exception:
                pass
        return ""

    @staticmethod
    def parse_file(filepath: Path = None, content: bytes = None) -> dict:
        """Parse an .eml file and extract searchable content.

        Args:
            filepath: Path to .eml file (reads from disk)
            content: Raw email bytes (avoids disk read if already loaded)
        """
        try:
            if content is not None:
                msg = email.message_from_bytes(content, policy=email_policy)
            elif filepath is not None:
                with open(filepath, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=email_policy)
            else:
                raise ValueError("Must provide filepath or content")
        except Exception as e:
            # If even parsing fails, return minimal info
            return {
                "subject": "",
                "sender": "",
                "recipients": "",
                "date_str": "",
                "body": f"[Parse error: {e}]",
                "attachments": "",
            }

        # Extract headers safely
        subject = EmailParser._safe_get_header(msg, "Subject")
        sender = EmailParser._safe_get_header(msg, "From")

        # Combine all recipient fields
        recipients = []
        for header in ["To", "Cc", "Bcc"]:
            val = EmailParser._safe_get_header(msg, header)
            if val:
                recipients.append(val)
        recipients_str = ", ".join(recipients)

        date_str = EmailParser._safe_get_header(msg, "Date")

        # Extract body text
        body_parts = []
        attachments = []

        try:
            if msg.is_multipart():
                for part in msg.walk():
                    try:
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition", ""))

                        # Get attachment filenames
                        if "attachment" in content_disposition:
                            try:
                                filename = part.get_filename()
                                if filename:
                                    attachments.append(EmailParser._sanitize_header(filename))
                            except Exception:
                                pass

                        # Extract text content
                        if content_type == "text/plain":
                            text = EmailParser._safe_get_content(part)
                            if text:
                                body_parts.append(text)
                        elif content_type == "text/html" and not body_parts:
                            # Only use HTML if no plain text
                            text = EmailParser._safe_get_content(part)
                            if text:
                                # Strip HTML tags for indexing
                                text = re.sub(r'<[^>]+>', ' ', text)
                                text = re.sub(r'\s+', ' ', text)
                                body_parts.append(text)
                    except Exception:
                        continue
            else:
                text = EmailParser._safe_get_content(msg)
                if text:
                    if msg.get_content_type() == "text/html":
                        text = re.sub(r'<[^>]+>', ' ', text)
                        text = re.sub(r'\s+', ' ', text)
                    body_parts.append(text)
        except Exception:
            pass

        return {
            "subject": subject,
            "sender": sender,
            "recipients": recipients_str,
            "date_str": date_str,
            "body": "\n".join(body_parts),
            "attachments": ", ".join(attachments),
        }


class GmailArchive:
    """Main Gmail archive class."""

    def __init__(self, archive_dir: Path, config: Dict[str, Any] = None):
        self.archive_dir = archive_dir
        self.emails_dir = archive_dir / "emails"
        self.keychain = KeychainStorage(KEYCHAIN_SERVICE)
        self.db = ArchiveDatabase(archive_dir)
        self.service = None
        self.config = config or {}

        # Config options with defaults
        self.include_labels = self.config.get("include_labels", True)

    def authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2."""
        creds = self.keychain.load_token()

        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            try:
                creds.refresh(Request())
                self.keychain.save_token(creds)
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None

        if not creds or not creds.valid:
            # Check for client credentials in Keychain
            client_credentials = self.keychain.load_client_credentials()
            if not client_credentials:
                print("\n❌ Error: No OAuth credentials found in Keychain")
                print("\nRun 'ownmail setup' first to configure credentials.")
                sys.exit(1)

            print("\nStarting OAuth authentication flow...")
            print("A browser window will open for you to authorize access.\n")

            # Create flow from Keychain-stored credentials
            client_config = json.loads(client_credentials)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            self.keychain.save_token(creds)

        self.service = build("gmail", "v1", credentials=creds)
        print("✓ Authenticated with Gmail API")

    def get_new_message_ids(self) -> list:
        """Get list of message IDs to download."""
        history_id = self.db.get_history_id()
        downloaded_ids = self.db.get_downloaded_ids()

        if history_id:
            try:
                new_ids = self._get_messages_since_history(history_id, downloaded_ids)
                if new_ids is not None:
                    return new_ids
            except HttpError as e:
                if e.resp.status == 404:
                    print("History expired, performing full sync...")
                else:
                    raise

        print("Fetching all message IDs...")
        all_ids = self._get_all_message_ids()
        new_ids = [mid for mid in all_ids if mid not in downloaded_ids]
        return new_ids

    def _get_messages_since_history(
        self, history_id: str, downloaded_ids: set
    ) -> Optional[list]:
        """Get new messages since the given history ID."""
        new_ids = []
        page_token = None

        while True:
            response = (
                self.service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
                .execute()
            )

            if "history" in response:
                for history in response["history"]:
                    if "messagesAdded" in history:
                        for msg in history["messagesAdded"]:
                            msg_id = msg["message"]["id"]
                            if msg_id not in downloaded_ids:
                                new_ids.append(msg_id)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return new_ids

    def _get_all_message_ids(self) -> list:
        """Get all message IDs from the mailbox."""
        all_ids = []
        page_token = None

        while True:
            response = (
                self.service.users()
                .messages()
                .list(userId="me", pageToken=page_token, maxResults=500)
                .execute()
            )

            if "messages" in response:
                all_ids.extend([msg["id"] for msg in response["messages"]])
                print(f"  Found {len(all_ids)} messages...", end="\r")

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        print(f"  Found {len(all_ids)} total messages")
        return all_ids

    def _get_labels_for_message(self, message_id: str) -> List[str]:
        """Fetch Gmail labels for a message."""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="metadata", metadataHeaders=[])
                .execute()
            )
            label_ids = message.get("labelIds", [])

            # Convert label IDs to readable names
            # System labels are like INBOX, SENT, IMPORTANT, etc.
            # User labels need to be looked up (cached)
            return self._resolve_label_names(label_ids)
        except HttpError:
            return []

    def _resolve_label_names(self, label_ids: List[str]) -> List[str]:
        """Convert label IDs to human-readable names."""
        # Cache labels on first use
        if not hasattr(self, "_label_cache"):
            self._label_cache = {}
            try:
                result = self.service.users().labels().list(userId="me").execute()
                for label in result.get("labels", []):
                    self._label_cache[label["id"]] = label["name"]
            except HttpError:
                pass

        names = []
        for lid in label_ids:
            if lid in self._label_cache:
                names.append(self._label_cache[lid])
            else:
                # Fallback to ID if not found
                names.append(lid)
        return names

    def _inject_labels(self, message_id: str, raw_data: bytes) -> bytes:
        """Inject X-Gmail-Labels header into raw email data."""
        labels = self._get_labels_for_message(message_id)
        if not labels:
            return raw_data

        # Create the header line
        labels_str = ", ".join(labels)
        header_line = f"X-Gmail-Labels: {labels_str}\r\n".encode()

        # Insert after the first line (usually "Received:" or similar)
        # Find the first \r\n and insert after it
        first_newline = raw_data.find(b"\r\n")
        if first_newline == -1:
            first_newline = raw_data.find(b"\n")
            if first_newline == -1:
                return raw_data
            # Use \n style
            header_line = f"X-Gmail-Labels: {labels_str}\n".encode()
            return raw_data[:first_newline + 1] + header_line + raw_data[first_newline + 1:]

        return raw_data[:first_newline + 2] + header_line + raw_data[first_newline + 2:]

    def download_message(self, message_id: str, include_labels: bool = None, db_conn: sqlite3.Connection = None) -> Optional[Path]:
        """Download a single message and save it atomically.

        Args:
            db_conn: Optional database connection for batching. If None, creates one.
        """
        if include_labels is None:
            include_labels = self.include_labels

        try:
            # Fetch raw email
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )

            raw_data = base64.urlsafe_b64decode(message["raw"])

            # Fetch labels if enabled
            if include_labels:
                raw_data = self._inject_labels(message_id, raw_data)

            email_msg = email.message_from_bytes(raw_data)
            date_str = email_msg.get("Date", "")

            try:
                from email.utils import parsedate_to_datetime
                msg_date = parsedate_to_datetime(date_str)
                date_prefix = msg_date.strftime("%Y%m%d_%H%M%S")
                year_month = msg_date.strftime("%Y/%m")
            except Exception:
                date_prefix = "unknown"
                year_month = "unknown"

            msg_dir = self.emails_dir / year_month
            msg_dir.mkdir(parents=True, exist_ok=True)

            safe_id = hashlib.sha256(message_id.encode()).hexdigest()[:12]
            filename = f"{date_prefix}_{safe_id}.eml"
            filepath = msg_dir / filename

            # Atomic write: write to temp file, then rename
            # This prevents corrupt partial files if interrupted
            fd, temp_path = tempfile.mkstemp(dir=msg_dir, suffix=".tmp")
            try:
                os.write(fd, raw_data)
                os.close(fd)
                os.rename(temp_path, filepath)
            except:
                os.close(fd)
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

            # Compute content hash for integrity verification
            content_hash = hashlib.sha256(raw_data).hexdigest()

            rel_path = str(filepath.relative_to(self.archive_dir))
            self.db.mark_downloaded(message_id=message_id, filename=rel_path, content_hash=content_hash, conn=db_conn)

            return filepath

        except HttpError as e:
            print(f"\n  Error downloading {message_id}: {e}")
            return None

    def index_email(self, message_id: str, filepath: Path, update_hash: bool = True, debug: bool = False, skip_delete: bool = False) -> bool:
        """Index an email for full-text search.

        Args:
            message_id: The message ID
            filepath: Path to the .eml file
            update_hash: If True, also compute and update content_hash and indexed_hash
            debug: If True, print timing information
            skip_delete: If True, skip DELETE before INSERT (for new emails not yet in FTS)

        Returns:
            True if successful, False otherwise
        """
        try:
            t0 = time.time()

            # Read file content once for both parsing and hashing
            with open(filepath, "rb") as f:
                content = f.read()
            t_read = time.time() - t0

            # Compute hash
            t0 = time.time()
            new_hash = hashlib.sha256(content).hexdigest() if update_hash else None
            t_hash = time.time() - t0

            # Parse email (using already-loaded content)
            t0 = time.time()
            parsed = EmailParser.parse_file(content=content)
            t_parse = time.time() - t0

            # Use shared connection if available (for batching)
            conn = getattr(self, '_batch_conn', None)

            # Index in FTS
            t0 = time.time()
            self.db.index_email(
                message_id=message_id,
                subject=parsed["subject"],
                sender=parsed["sender"],
                recipients=parsed["recipients"],
                date_str=parsed["date_str"],
                body=parsed["body"],
                attachments=parsed["attachments"],
                conn=conn,
                skip_delete=skip_delete,
            )
            t_fts = time.time() - t0

            # Update hashes (use shared connection if available)
            t0 = time.time()
            if update_hash and new_hash:
                if conn:
                    conn.execute(
                        "UPDATE emails SET content_hash = ?, indexed_hash = ? WHERE message_id = ?",
                        (new_hash, new_hash, message_id)
                    )
                else:
                    with sqlite3.connect(self.db.db_path) as c:
                        c.execute(
                            "UPDATE emails SET content_hash = ?, indexed_hash = ? WHERE message_id = ?",
                            (new_hash, new_hash, message_id)
                        )
                        c.commit()
            t_update = time.time() - t0

            if debug:
                total = t_read + t_hash + t_parse + t_fts + t_update
                print(f"\n    DEBUG: read={t_read*1000:.0f}ms hash={t_hash*1000:.0f}ms parse={t_parse*1000:.0f}ms fts={t_fts*1000:.0f}ms update={t_update*1000:.0f}ms TOTAL={total*1000:.0f}ms")

            return True
        except Exception as e:
            print(f"\n  Error indexing {filepath}: {e}")
            return False

    def update_history_id(self) -> None:
        """Update the stored history ID for future incremental syncs."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            history_id = profile.get("historyId")
            if history_id:
                self.db.set_history_id(history_id)
        except HttpError as e:
            print(f"Warning: Could not update history ID: {e}")

    def cmd_backup(self) -> None:
        """Run the backup process."""
        print("\n" + "=" * 50)
        print("ownmail - Backup")
        print("=" * 50 + "\n")

        self.authenticate()

        stats = self.db.get_stats()
        print(f"Archive location: {self.archive_dir}")
        print(f"Previously backed up: {stats['total_emails']} emails")

        print("\nChecking for new emails...")
        new_message_ids = self.get_new_message_ids()

        if not new_message_ids:
            print("\n✓ No new emails to download. Archive is up to date!")
            self.update_history_id()
            return

        print(f"\nFound {len(new_message_ids)} new emails to download")
        print("(Press Ctrl-C to stop - progress is saved, you can resume anytime)\n")

        success_count = 0
        error_count = 0
        interrupted = False
        start_time = time.time()
        last_commit_count = 0
        COMMIT_INTERVAL = 10  # Commit every N emails (lower than reindex since download is slower)

        # Handle Ctrl-C gracefully
        def signal_handler(signum, frame):
            nonlocal interrupted
            if interrupted:
                # Second Ctrl-C, exit immediately
                print("\n\nForce quit.")
                sys.exit(1)
            interrupted = True
            print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

        original_handler = signal.signal(signal.SIGINT, signal_handler)

        # Use a shared connection for batching
        self._batch_conn = sqlite3.connect(self.db.db_path)
        self._batch_conn.execute("PRAGMA journal_mode = WAL")
        self._batch_conn.execute("PRAGMA synchronous = NORMAL")

        # Track rate for display during downloads
        last_rate = 0.0
        last_eta_str = "..."

        try:
            for i, msg_id in enumerate(new_message_ids, 1):
                if interrupted:
                    break

                # Show stats from previous iteration while downloading
                if success_count > 0 and last_rate > 0:
                    print(f"\r\033[K  [{i}/{len(new_message_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | downloading...", end="", flush=True)
                else:
                    print(f"\r\033[K  [{i}/{len(new_message_ids)}] downloading...", end="", flush=True)

                filepath = self.download_message(msg_id, db_conn=self._batch_conn)
                if filepath:
                    # Show file size for progress visibility
                    size_bytes = filepath.stat().st_size
                    if size_bytes > 1_000_000:
                        size_str = f"{size_bytes / 1_000_000:.1f}MB"
                    elif size_bytes > 1_000:
                        size_str = f"{size_bytes / 1_000:.0f}KB"
                    else:
                        size_str = f"{size_bytes}B"
                    print(f"\r\033[K  [{i}/{len(new_message_ids)}] {size_str:>7} - indexing...", end="", flush=True)
                    self.index_email(msg_id, filepath, skip_delete=True)
                    success_count += 1

                    # Commit periodically
                    if success_count - last_commit_count >= COMMIT_INTERVAL:
                        self._batch_conn.commit()
                        last_commit_count = success_count

                    # Calculate progress stats
                    elapsed = time.time() - start_time
                    last_rate = success_count / elapsed if elapsed > 0 else 0
                    remaining = len(new_message_ids) - i
                    eta = remaining / last_rate if last_rate > 0 else 0

                    # Format ETA
                    if i < 3:
                        last_eta_str = "..."
                    elif eta > 3600:
                        last_eta_str = f"{eta/3600:.1f}h"
                    elif eta > 60:
                        last_eta_str = f"{eta/60:.0f}m"
                    else:
                        last_eta_str = f"{eta:.0f}s"

                    print(f"\r\033[K  [{i}/{len(new_message_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | {size_str:>7}", end="", flush=True)
                else:
                    error_count += 1
        finally:
            # Commit any remaining and close
            self._batch_conn.commit()
            self._batch_conn.close()
            self._batch_conn = None
            signal.signal(signal.SIGINT, original_handler)

        # Only update history_id if backup completed fully (not interrupted)
        if not interrupted:
            self.update_history_id()

        print("\n" + "-" * 50)
        if interrupted:
            remaining = len(new_message_ids) - success_count - error_count
            print("Backup Paused!")
            print(f"  Downloaded: {success_count} emails")
            print(f"  Remaining: {remaining} emails")
            print("\n  Run 'backup' again to resume.")
        else:
            print("Backup Complete!")
            print(f"  Downloaded: {success_count} emails")
        if error_count > 0:
            print(f"  Errors: {error_count}")

        final_stats = self.db.get_stats()
        print(f"  Total archived: {final_stats['total_emails']} emails")
        print("-" * 50 + "\n")

    def cmd_search(self, query: str) -> None:
        """Search archived emails."""
        print(f"\nSearching for: {query}\n")

        results = self.db.search(query)

        if not results:
            print("No results found.")
            return

        print(f"Found {len(results)} results:\n")
        print("-" * 70)

        for _msg_id, filename, subject, sender, date_str, snippet in results:
            print(f"From: {sender}")
            print(f"Date: {date_str}")
            print(f"Subject: {subject}")
            print(f"File: {filename}")
            if snippet:
                # Clean up snippet markers
                snippet = snippet.replace(">>>", "\033[1m").replace("<<<", "\033[0m")
                print(f"Snippet: ...{snippet}...")
            print("-" * 70)

    def cmd_stats(self) -> None:
        """Show archive statistics."""
        stats = self.db.get_stats()

        print("\n" + "=" * 50)
        print("ownmail - Statistics")
        print("=" * 50)
        print(f"\nArchive location: {self.archive_dir}")
        print(f"Total emails: {stats['total_emails']}")
        print(f"Indexed for search: {stats['indexed_emails']}")

        if stats['oldest_backup']:
            print(f"First backup: {stats['oldest_backup']}")
        if stats['newest_backup']:
            print(f"Latest backup: {stats['newest_backup']}")

        # Calculate disk usage
        total_size = 0
        email_count = 0
        for eml_file in self.emails_dir.rglob("*.eml"):
            total_size += eml_file.stat().st_size
            email_count += 1

        if total_size > 0:
            if total_size > 1_000_000_000:
                size_str = f"{total_size / 1_000_000_000:.2f} GB"
            elif total_size > 1_000_000:
                size_str = f"{total_size / 1_000_000:.2f} MB"
            else:
                size_str = f"{total_size / 1_000:.2f} KB"
            print(f"Disk usage: {size_str}")

        print()

    def cmd_setup(self, credentials_file: Optional[Path] = None) -> None:
        """Set up OAuth credentials."""
        print("\n" + "=" * 50)
        print("ownmail - Setup")
        print("=" * 50 + "\n")

        if self.keychain.has_client_credentials():
            print("⚠ OAuth credentials already exist in Keychain.")
            response = input("Replace existing credentials? [y/N]: ").strip().lower()
            if response != "y":
                print("Setup cancelled.")
                return

        if credentials_file:
            # Import from file
            if not credentials_file.exists():
                print(f"❌ File not found: {credentials_file}")
                sys.exit(1)

            with open(credentials_file) as f:
                credentials_json = f.read()

            print(f"Importing credentials from: {credentials_file}")
        else:
            # Prompt for paste
            print("To set up Gmail API access:")
            print("1. Go to https://console.cloud.google.com/")
            print("2. Create a new project or select an existing one")
            print("3. Enable the Gmail API")
            print("4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
            print("5. Select 'Desktop application' as the application type")
            print("6. Download the JSON file")
            print("")
            print("Paste the contents of the downloaded JSON file below.")
            print("(Paste the JSON, then press Enter twice to finish)")
            print("")

            lines = []
            empty_count = 0
            while empty_count < 1:
                try:
                    line = input()
                    if line == "":
                        empty_count += 1
                    else:
                        empty_count = 0
                        lines.append(line)
                except EOFError:
                    break

            credentials_json = "\n".join(lines)

        try:
            self.keychain.save_client_credentials(credentials_json)
            print("\n✓ OAuth credentials saved to macOS Keychain")
            print("\nYou can now run: ownmail backup")

            # Remind user to delete the source file if imported from file
            if credentials_file:
                print(f"\n⚠ Remember to securely delete: {credentials_file}")
                print(f"  rm {credentials_file}")
        except ValueError as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)

    def cmd_reindex(self, file_path: Optional[Path] = None, pattern: Optional[str] = None, force: bool = False, debug: bool = False) -> None:
        """Rebuild the search index.

        By default, only indexes emails that have changed (content_hash != indexed_hash).
        This makes reindex resumable - if cancelled, just run again to continue.

        Args:
            file_path: Index only this specific file
            pattern: Index only files matching this glob pattern (e.g., "2024/09/*")
            force: If True, reindex all emails regardless of indexed_hash
            debug: If True, show timing info for each email
        """
        self._debug = debug
        print("\n" + "=" * 50)
        print("ownmail - Reindex")
        print("=" * 50 + "\n")

        # Single file mode
        if file_path:
            if not file_path.exists():
                print(f"File not found: {file_path}")
                return

            # Find message_id for this file
            rel_path = None
            try:
                rel_path = file_path.relative_to(self.archive_dir)
            except ValueError:
                # file_path might be absolute from different base
                pass

            if rel_path:
                with sqlite3.connect(self.db.db_path) as conn:
                    result = conn.execute(
                        "SELECT message_id FROM emails WHERE filename = ?",
                        (str(rel_path),)
                    ).fetchone()
                    if result:
                        msg_id = result[0]
                        print(f"Indexing: {file_path.name}")
                        if self.index_email(msg_id, file_path):
                            print("✓ Indexed successfully")
                        else:
                            print("✗ Failed to index")
                        return

            # If not in DB, use filename as message_id
            print(f"Indexing: {file_path.name}")
            if self.index_email(file_path.stem, file_path):
                print("✓ Indexed successfully")
            else:
                print("✗ Failed to index")
            return

        # Force mode: clear indexed_hash so all emails are re-indexed
        if force:
            print("Force mode: will reindex all emails")
            with sqlite3.connect(self.db.db_path) as conn:
                conn.execute("UPDATE emails SET indexed_hash = NULL")
                conn.commit()

        # Get emails to index (where indexed_hash != content_hash or either is NULL)
        with sqlite3.connect(self.db.db_path) as conn:
            if pattern:
                # Use LIKE for pattern matching
                like_pattern = pattern.replace("*", "%").replace("?", "_")
                emails = conn.execute(
                    """SELECT message_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE filename LIKE ?
                       AND (indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash)""",
                    (f"emails/{like_pattern}",)
                ).fetchall()
                total_matching = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE filename LIKE ?",
                    (f"emails/{like_pattern}",)
                ).fetchone()[0]
                print(f"Pattern '{pattern}': {len(emails)} need indexing (of {total_matching} matching)")
            else:
                emails = conn.execute(
                    """SELECT message_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash"""
                ).fetchall()
                total_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                already_indexed = total_emails - len(emails)
                if already_indexed > 0:
                    print(f"Skipping {already_indexed} already-indexed emails")

        if not emails:
            print("All emails are already indexed. Use --force to reindex everything.")
            return

        # Track IDs that need old FTS entries deleted (already indexed, being re-indexed)
        reindex_ids = [msg_id for msg_id, _, _, indexed_hash in emails if indexed_hash is not None]

        print(f"Indexing {len(emails)} emails...")
        if reindex_ids:
            print(f"  ({len(reindex_ids)} will be re-indexed)")
        print("(Press Ctrl-C to pause - progress is saved, run again to resume)\n")

        success_count = 0
        error_count = 0
        interrupted = False
        start_time = time.time()
        last_commit_count = 0
        COMMIT_INTERVAL = 50  # Commit every N emails
        successfully_reindexed = []  # Track which re-indexed emails succeeded (need old entry deleted)

        def signal_handler(signum, frame):
            nonlocal interrupted
            interrupted = True
            print("\n\n⏸ Stopping after current email...")

        original_handler = signal.signal(signal.SIGINT, signal_handler)

        # Use a shared connection for batching (much faster on slow disks)
        self._batch_conn = sqlite3.connect(self.db.db_path)
        # WAL mode is faster for writes and crash-safe
        self._batch_conn.execute("PRAGMA journal_mode = WAL")
        self._batch_conn.execute("PRAGMA synchronous = NORMAL")

        try:
            for i, (msg_id, filename, _content_hash, indexed_hash) in enumerate(emails, 1):
                if interrupted:
                    break

                filepath = self.archive_dir / filename
                short_name = Path(filename).name[:40]

                # Show what we're working on
                print(f"\r\033[K  [{i}/{len(emails)}] {short_name}", end="", flush=True)

                if not filepath.exists():
                    error_count += 1
                    continue

                # Always skip DELETE - we handle it in batch upfront
                if self.index_email(msg_id, filepath, update_hash=True, debug=self._debug, skip_delete=True):
                    success_count += 1
                    # Track re-indexed emails that need old FTS entry deleted
                    if indexed_hash is not None:
                        successfully_reindexed.append(msg_id)
                else:
                    error_count += 1

                # Commit periodically to save progress
                if success_count - last_commit_count >= COMMIT_INTERVAL:
                    self._batch_conn.commit()
                    last_commit_count = success_count

                # Calculate and show progress stats after processing
                elapsed = time.time() - start_time
                rate = success_count / elapsed if elapsed > 0 else 0
                remaining = len(emails) - i
                eta = remaining / rate if rate > 0 else 0

                # Format ETA (show "..." for first few to get stable estimate)
                if i < 5:
                    eta_str = "..."
                elif eta > 3600:
                    eta_str = f"{eta/3600:.1f}h"
                elif eta > 60:
                    eta_str = f"{eta/60:.0f}m"
                else:
                    eta_str = f"{eta:.0f}s"

                # Update progress line
                print(f"\r\033[K  [{i}/{len(emails)}] {rate:.1f}/s | ETA {eta_str:>5} | {short_name}", end="", flush=True)
        finally:
            # Commit any remaining inserts
            self._batch_conn.commit()

            # Delete old FTS entries for successfully re-indexed emails (batch delete at end)
            if successfully_reindexed:
                print(f"\n  Cleaning up {len(successfully_reindexed)} old FTS entries...", end="", flush=True)
                t0 = time.time()
                # FTS5 creates rowid, old entries have lower rowid than new ones
                # Delete entries where message_id matches but rowid is not the max for that message_id
                for msg_id in successfully_reindexed:
                    self._batch_conn.execute("""
                        DELETE FROM emails_fts WHERE message_id = ? AND rowid < (
                            SELECT MAX(rowid) FROM emails_fts WHERE message_id = ?
                        )
                    """, (msg_id, msg_id))
                self._batch_conn.commit()
                print(f" done ({time.time()-t0:.1f}s)")

            self._batch_conn.close()
            self._batch_conn = None
            signal.signal(signal.SIGINT, original_handler)

        elapsed_total = time.time() - start_time
        print("\n" + "-" * 50)
        if interrupted:
            remaining = len(emails) - success_count - error_count
            print("Reindex Paused!")
            print(f"  Indexed: {success_count} emails in {elapsed_total:.1f}s")
            print(f"  Remaining: {remaining} emails")
            print("\n  Run 'ownmail reindex' again to resume.")
        else:
            print("Reindex Complete!")
            print(f"  Indexed: {success_count} emails in {elapsed_total:.1f}s")
        if error_count > 0:
            print(f"  Errors: {error_count}")
        print("-" * 50 + "\n")

    def cmd_add_labels(self) -> None:
        """Add Gmail labels to existing downloaded emails."""
        print("\n" + "=" * 50)
        print("ownmail - Add Labels")
        print("=" * 50 + "\n")

        self.authenticate()

        # Get all downloaded emails
        with sqlite3.connect(self.db.db_path) as conn:
            emails = conn.execute(
                "SELECT message_id, filename FROM emails"
            ).fetchall()

        if not emails:
            print("No emails to process.")
            return

        print(f"Adding labels to {len(emails)} emails...")
        print("(Press Ctrl-C to stop - already processed files are saved)\n")

        success_count = 0
        skip_count = 0
        error_count = 0
        interrupted = False

        def signal_handler(signum, frame):
            nonlocal interrupted
            if interrupted:
                print("\n\nForce quit.")
                sys.exit(1)
            interrupted = True
            print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

        original_handler = signal.signal(signal.SIGINT, signal_handler)

        try:
            for i, (msg_id, filename) in enumerate(emails, 1):
                if interrupted:
                    break

                filepath = self.archive_dir / filename
                if not filepath.exists():
                    error_count += 1
                    continue

                # Check if already has labels
                with open(filepath, "rb") as f:
                    first_bytes = f.read(1000)
                    if b"X-Gmail-Labels:" in first_bytes:
                        skip_count += 1
                        continue

                print(f"  [{i}/{len(emails)}] Fetching labels...", end="\r")

                try:
                    # Get labels for this message
                    labels = self._get_labels_for_message(msg_id)
                    if not labels:
                        skip_count += 1
                        continue

                    # Read existing email
                    with open(filepath, "rb") as f:
                        raw_data = f.read()

                    # Inject labels header
                    labels_str = ", ".join(labels)
                    header_line = f"X-Gmail-Labels: {labels_str}\r\n".encode()

                    first_newline = raw_data.find(b"\r\n")
                    if first_newline == -1:
                        first_newline = raw_data.find(b"\n")
                        if first_newline != -1:
                            header_line = f"X-Gmail-Labels: {labels_str}\n".encode()
                            new_data = raw_data[:first_newline + 1] + header_line + raw_data[first_newline + 1:]
                        else:
                            skip_count += 1
                            continue
                    else:
                        new_data = raw_data[:first_newline + 2] + header_line + raw_data[first_newline + 2:]

                    # Atomic write
                    fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
                    try:
                        os.write(fd, new_data)
                        os.close(fd)
                        os.rename(temp_path, filepath)
                        success_count += 1
                    except:
                        os.close(fd)
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        raise

                except HttpError as e:
                    print(f"\n  Error processing {msg_id}: {e}")
                    error_count += 1

        finally:
            signal.signal(signal.SIGINT, original_handler)

        print("\n" + "-" * 50)
        if interrupted:
            print("Add Labels Paused!")
        else:
            print("Add Labels Complete!")
        print(f"  Updated: {success_count} emails")
        print(f"  Skipped (already had labels or no labels): {skip_count}")
        if error_count > 0:
            print(f"  Errors: {error_count}")
        print("-" * 50 + "\n")

    def _print_file_list(self, files: list, label: str, verbose: bool, max_show: int = 5) -> None:
        """Helper to print a list of files with truncation unless verbose."""
        if not files:
            return
        print(f"  {label}: {len(files)}")
        show_count = len(files) if verbose else min(len(files), max_show)
        for f in files[:show_count]:
            print(f"      {f}")
        if not verbose and len(files) > max_show:
            print(f"      ... and {len(files) - max_show} more (use --verbose to show all)")

    def cmd_verify(self, verbose: bool = False) -> None:
        """Verify integrity of downloaded emails against stored hashes."""
        print("\n" + "=" * 50)
        print("ownmail - Verify Integrity")
        print("=" * 50 + "\n")

        # Get all downloaded emails with hashes
        with sqlite3.connect(self.db.db_path) as conn:
            emails = conn.execute(
                "SELECT message_id, filename, content_hash FROM emails"
            ).fetchall()

        if not emails:
            print("No emails to verify.")
            return

        total = len(emails)
        ok_count = 0
        missing_count = 0
        corrupted_count = 0
        no_hash_count = 0
        corrupted_files = []
        missing_files = []
        indexed_files = set()

        print(f"Verifying {total} indexed emails...\n")

        for i, (_msg_id, filename, stored_hash) in enumerate(emails, 1):
            print(f"  [{i}/{total}] Verifying indexed...", end="\r")

            indexed_files.add(filename)
            filepath = self.archive_dir / filename

            if not filepath.exists():
                missing_count += 1
                missing_files.append(filename)
                continue

            if not stored_hash:
                no_hash_count += 1
                continue

            # Compute current hash
            with open(filepath, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()

            if current_hash == stored_hash:
                ok_count += 1
            else:
                corrupted_count += 1
                corrupted_files.append(filename)

        # Check for orphaned files (on disk but not in index)
        print("\n  Scanning for orphaned files...", end="\r")
        orphaned_files = []
        for eml_file in self.emails_dir.rglob("*.eml"):
            rel_path = str(eml_file.relative_to(self.archive_dir))
            if rel_path not in indexed_files:
                orphaned_files.append(rel_path)

        print("\n" + "-" * 50)
        print("Verification Complete!")
        print(f"  ✓ OK: {ok_count}")
        if no_hash_count > 0:
            print(f"  ? No hash stored: {no_hash_count} (run 'rehash' to compute)")
        self._print_file_list(missing_files, "✗ In index but missing from disk", verbose)
        self._print_file_list(orphaned_files, "? On disk but not in index", verbose)
        self._print_file_list(corrupted_files, "✗ CORRUPTED (hash mismatch)", verbose)

        if missing_count == 0 and corrupted_count == 0 and len(orphaned_files) == 0 and no_hash_count == 0:
            print("\n  ✓ All files verified successfully!")
        print("-" * 50 + "\n")

    def cmd_rehash(self) -> None:
        """Compute and store hashes for emails that don't have them."""
        print("\n" + "=" * 50)
        print("ownmail - Compute Hashes")
        print("=" * 50 + "\n")

        # Get emails without hashes
        with sqlite3.connect(self.db.db_path) as conn:
            emails = conn.execute(
                "SELECT message_id, filename FROM emails WHERE content_hash IS NULL"
            ).fetchall()

        if not emails:
            print("All emails already have hashes.")
            return

        print(f"Computing hashes for {len(emails)} emails...\n")

        success_count = 0
        error_count = 0

        for i, (msg_id, filename) in enumerate(emails, 1):
            print(f"  [{i}/{len(emails)}] Hashing...", end="\r")

            filepath = self.archive_dir / filename

            if not filepath.exists():
                error_count += 1
                continue

            with open(filepath, "rb") as f:
                content_hash = hashlib.sha256(f.read()).hexdigest()

            with sqlite3.connect(self.db.db_path) as conn:
                conn.execute(
                    "UPDATE emails SET content_hash = ? WHERE message_id = ?",
                    (content_hash, msg_id)
                )
                conn.commit()

            success_count += 1

        print("\n" + "-" * 50)
        print("Rehash Complete!")
        print(f"  Hashed: {success_count} emails")
        if error_count > 0:
            print(f"  Errors (missing files): {error_count}")
        print("-" * 50 + "\n")

    def cmd_sync_check(self, verbose: bool = False) -> None:
        """Compare local archive with Gmail server."""
        print("\n" + "=" * 50)
        print("ownmail - Sync Check")
        print("=" * 50 + "\n")

        self.authenticate()

        # Get all message IDs from Gmail
        print("Fetching message IDs from Gmail...")
        gmail_ids = set(self._get_all_message_ids())

        # Get all local message IDs
        local_ids = self.db.get_downloaded_ids()

        print(f"\nGmail: {len(gmail_ids)} emails")
        print(f"Local: {len(local_ids)} emails\n")

        # Find differences
        on_gmail_not_local = gmail_ids - local_ids
        on_local_not_gmail = local_ids - gmail_ids
        in_sync = gmail_ids & local_ids

        print("-" * 50)
        print("Sync Check Complete!")
        print(f"  ✓ In sync: {len(in_sync)}")

        # For displaying, we need filenames for local-only, but message IDs for gmail-only
        if on_gmail_not_local:
            print(f"  ↓ On Gmail but not local: {len(on_gmail_not_local)}")
            show_count = len(on_gmail_not_local) if verbose else min(len(on_gmail_not_local), 5)
            for msg_id in list(on_gmail_not_local)[:show_count]:
                print(f"      {msg_id}")
            if not verbose and len(on_gmail_not_local) > 5:
                print(f"      ... and {len(on_gmail_not_local) - 5} more (use --verbose to show all)")
            print("\n  Run 'backup' to download these emails.")

        if on_local_not_gmail:
            # Get filenames for these
            with sqlite3.connect(self.db.db_path) as conn:
                local_only_files = []
                for msg_id in on_local_not_gmail:
                    result = conn.execute(
                        "SELECT filename FROM emails WHERE message_id = ?", (msg_id,)
                    ).fetchone()
                    if result:
                        local_only_files.append(f"{result[0]} ({msg_id})")
                    else:
                        local_only_files.append(msg_id)

            print(f"  ✗ On local but not on Gmail (deleted from server?): {len(on_local_not_gmail)}")
            show_count = len(local_only_files) if verbose else min(len(local_only_files), 5)
            for f in local_only_files[:show_count]:
                print(f"      {f}")
            if not verbose and len(local_only_files) > 5:
                print(f"      ... and {len(local_only_files) - 5} more (use --verbose to show all)")

        if not on_gmail_not_local and not on_local_not_gmail:
            print("\n  ✓ Local archive is fully in sync with Gmail!")
        print("-" * 50 + "\n")

    def cmd_db_check(self, fix: bool = False, verbose: bool = False) -> None:
        """Check database integrity and optionally fix issues.

        Checks for:
        - Duplicate FTS entries (same message_id multiple times)
        - Orphaned FTS entries (in FTS but not in emails table)
        - Missing FTS entries (in emails but not in FTS)
        - indexed_hash mismatches
        """
        print("\n" + "=" * 50)
        print("ownmail - Database Check")
        print("=" * 50 + "\n")

        issues_found = 0
        issues_fixed = 0

        with sqlite3.connect(self.db.db_path) as conn:
            # 1. Check for duplicate FTS entries
            print("Checking for duplicate FTS entries...")
            duplicates = conn.execute("""
                SELECT message_id, COUNT(*) as cnt
                FROM emails_fts
                GROUP BY message_id
                HAVING cnt > 1
            """).fetchall()

            if duplicates:
                issues_found += len(duplicates)
                print(f"  ✗ Found {len(duplicates)} message_ids with duplicate FTS entries")
                if verbose:
                    for msg_id, cnt in duplicates[:10]:
                        print(f"      {msg_id}: {cnt} entries")
                    if len(duplicates) > 10:
                        print(f"      ... and {len(duplicates) - 10} more")

                if fix:
                    print("  Fixing: keeping only newest entry for each...", end="", flush=True)
                    # Single query: delete all rows that aren't the max rowid for their message_id
                    conn.execute("""
                        DELETE FROM emails_fts
                        WHERE rowid NOT IN (
                            SELECT MAX(rowid) FROM emails_fts GROUP BY message_id
                        )
                    """)
                    conn.commit()
                    issues_fixed += len(duplicates)
                    print(" done")
                    print(f"  ✓ Fixed {len(duplicates)} duplicates")
            else:
                print("  ✓ No duplicate FTS entries")

            # 2. Check for orphaned FTS entries (in FTS but not in emails)
            print("\nChecking for orphaned FTS entries...")
            # Use NOT IN instead of LEFT JOIN for better performance with FTS5
            orphaned_fts = conn.execute("""
                SELECT DISTINCT message_id
                FROM emails_fts
                WHERE message_id NOT IN (SELECT message_id FROM emails)
            """).fetchall()

            if orphaned_fts:
                orphaned_ids = [row[0] for row in orphaned_fts]
                issues_found += len(orphaned_ids)
                print(f"  ✗ Found {len(orphaned_ids)} FTS entries with no matching email record")
                if verbose:
                    for msg_id in orphaned_ids[:10]:
                        print(f"      {msg_id}")
                    if len(orphaned_ids) > 10:
                        print(f"      ... and {len(orphaned_ids) - 10} more")

                if fix:
                    print("  Fixing: removing orphaned FTS entries...")
                    for msg_id in orphaned_ids:
                        conn.execute("DELETE FROM emails_fts WHERE message_id = ?", (msg_id,))
                    conn.commit()
                    issues_fixed += len(orphaned_ids)
                    print(f"  ✓ Removed {len(orphaned_ids)} orphaned entries")
            else:
                print("  ✓ No orphaned FTS entries")

            # 3. Check for missing FTS entries (in emails but not in FTS)
            print("\nChecking for missing FTS entries...")
            # Use NOT IN instead of LEFT JOIN for better performance with FTS5
            missing_fts = conn.execute("""
                SELECT message_id, filename
                FROM emails
                WHERE message_id NOT IN (SELECT DISTINCT message_id FROM emails_fts)
            """).fetchall()

            if missing_fts:
                issues_found += len(missing_fts)
                print(f"  ✗ Found {len(missing_fts)} emails not in search index")
                if verbose:
                    for _, filename in missing_fts[:10]:
                        print(f"      {filename}")
                    if len(missing_fts) > 10:
                        print(f"      ... and {len(missing_fts) - 10} more")
                print("  → Run 'ownmail reindex' to index these emails")
            else:
                print("  ✓ All emails are in search index")

            # 4. Check indexed_hash vs content_hash mismatches
            print("\nChecking for index hash mismatches...")
            hash_mismatches = conn.execute("""
                SELECT message_id, filename
                FROM emails
                WHERE content_hash IS NOT NULL
                  AND indexed_hash IS NOT NULL
                  AND content_hash != indexed_hash
            """).fetchall()

            if hash_mismatches:
                issues_found += len(hash_mismatches)
                print(f"  ✗ Found {len(hash_mismatches)} emails where index is out of date")
                if verbose:
                    for _, filename in hash_mismatches[:10]:
                        print(f"      {filename}")
                    if len(hash_mismatches) > 10:
                        print(f"      ... and {len(hash_mismatches) - 10} more")
                print("  → Run 'ownmail reindex' to update these")
            else:
                print("  ✓ All indexed emails are up to date")

            # 5. Check for NULL hashes
            print("\nChecking for missing hashes...")
            null_content_hash = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE content_hash IS NULL"
            ).fetchone()[0]
            null_indexed_hash = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE indexed_hash IS NULL"
            ).fetchone()[0]

            if null_content_hash > 0:
                print(f"  ? {null_content_hash} emails without content_hash")
                print("  → Run 'ownmail rehash' to compute")
            if null_indexed_hash > 0:
                print(f"  ? {null_indexed_hash} emails without indexed_hash (not yet indexed)")
                print("  → Run 'ownmail reindex' to index")
            if null_content_hash == 0 and null_indexed_hash == 0:
                print("  ✓ All emails have hashes")

        # Summary
        print("\n" + "-" * 50)
        if issues_found == 0:
            print("Database Check Complete!")
            print("  ✓ No issues found")
        else:
            print("Database Check Complete!")
            print(f"  Issues found: {issues_found}")
            if fix:
                print(f"  Issues fixed: {issues_fixed}")
                if issues_found > issues_fixed:
                    print(f"  Remaining: {issues_found - issues_fixed} (run 'reindex' or 'rehash')")
            else:
                print("\n  Run with --fix to automatically fix fixable issues")
        print("-" * 50 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ownmail",
        description="ownmail - Own your mail. Backup and search your emails locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s setup                           First-time credential setup
  %(prog)s setup --credentials-file creds.json
  %(prog)s backup                          Download new emails
  %(prog)s backup --archive-dir /Volumes/Secure/ownmail
  %(prog)s search "invoice from:amazon"   Search emails
  %(prog)s search "subject:meeting"        Search by subject
  %(prog)s stats                           Show statistics
  %(prog)s reindex                         Index new/changed emails (resumable)
  %(prog)s reindex --force                 Reindex everything from scratch
  %(prog)s reindex --file path/to/email.eml   Reindex single file
  %(prog)s reindex --pattern "2024/09/*"      Reindex September 2024 only
  %(prog)s add-labels                      Add Gmail labels to existing emails
  %(prog)s verify                          Verify integrity of downloaded emails
  %(prog)s verify --verbose                Show full list of issues
  %(prog)s rehash                          Compute hashes for emails without them
  %(prog)s sync-check                      Compare local archive with server
  %(prog)s db-check                        Check database for issues
  %(prog)s db-check --fix                  Check and fix database issues

Config file (config.yaml):
    archive_dir: /Volumes/Secure/ownmail
    include_labels: true
        """,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: ./config.yaml)",
    )

    parser.add_argument(
        "--archive-dir",
        type=Path,
        help="Directory to store emails and database",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure OAuth credentials",
        description="Set up Gmail API OAuth credentials for the first time.",
        epilog="""
Examples:
  ownmail setup                              Interactive setup (paste JSON)
  ownmail setup --credentials-file creds.json   Import from file

After setup, you can delete the credentials JSON file.
Credentials are stored securely in your system keychain.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    setup_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Path to credentials JSON file (will be imported and can be deleted)",
    )

    # backup command
    subparsers.add_parser(
        "backup",
        help="Download new emails from Gmail",
        description="Download new emails from Gmail and index them for search.",
        epilog="""
Emails are saved as .eml files organized by year/month.
Progress is saved automatically - safe to Ctrl-C and resume.
Uses incremental sync to only download new emails.

Examples:
  ownmail backup
  ownmail backup --archive-dir /Volumes/Secure/ownmail
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search archived emails",
        description="Full-text search across all downloaded emails.",
        epilog="""
Supported search prefixes:
  from:       Search by sender (e.g., from:amazon)
  to:         Search by recipient
  subject:    Search in subject line only
  attachment: Search by attachment filename

Examples:
  ownmail search "invoice"
  ownmail search "from:amazon subject:order"
  ownmail search "attachment:pdf"
  ownmail search "meeting" --limit 100
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    search_parser.add_argument(
        "query",
        help="Search query (supports from:, to:, subject:, attachment: prefixes)",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of results (default: 50)",
    )

    # stats command
    subparsers.add_parser(
        "stats",
        help="Show archive statistics",
        description="Display statistics about your email archive.",
        epilog="""
Shows:
  - Total number of emails downloaded
  - Number of emails indexed for search
  - Date range of backups
  - Disk space used
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # reindex command
    reindex_parser = subparsers.add_parser(
        "reindex",
        help="Rebuild the search index",
        description="Rebuild the full-text search index from email files.",
        epilog="""
By default, only indexes emails that have changed (based on content hash).
This makes reindex resumable - safe to Ctrl-C and run again to continue.

Examples:
  ownmail reindex                    Index new/changed emails only
  ownmail reindex --force            Reindex everything from scratch
  ownmail reindex --file email.eml   Reindex a single file
  ownmail reindex --pattern "2024/*" Reindex all of 2024
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    reindex_parser.add_argument(
        "--file",
        type=Path,
        help="Index only this specific .eml file",
    )
    reindex_parser.add_argument(
        "--pattern",
        type=str,
        help="Index only files matching this pattern (e.g., '2024/09/*' or '2024/*')",
    )
    reindex_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Reindex all emails, even if already indexed",
    )
    reindex_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show timing debug info for each email",
    )

    # add-labels command
    subparsers.add_parser(
        "add-labels",
        help="Add Gmail labels to existing emails",
        description="Fetch Gmail labels and add them to existing downloaded emails.",
        epilog="""
Adds X-Gmail-Labels header to .eml files that don't have it.
Useful if you downloaded emails before label support was added.

Labels are stored in the email file itself, so they're preserved
even if you import the emails into another email client.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify integrity of downloaded emails",
        description="Verify that downloaded emails haven't been corrupted.",
        epilog="""
Checks:
  - Files exist on disk for all indexed emails
  - SHA256 hash matches the stored hash (detects corruption)
  - No orphaned files on disk (not in index)

Examples:
  ownmail verify              Quick summary
  ownmail verify --verbose    Show all issues in detail
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verify_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full list of issues instead of truncated",
    )

    # rehash command
    subparsers.add_parser(
        "rehash",
        help="Compute hashes for emails without them",
        description="Compute SHA256 content hashes for emails that don't have them.",
        epilog="""
Hashes are used for:
  - Integrity verification (detect corruption)
  - Tracking which emails have been indexed
  - Detecting file changes for re-indexing

Run this if you have old emails without hashes (from before
hash support was added).
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # sync-check command
    sync_check_parser = subparsers.add_parser(
        "sync-check",
        help="Compare local archive with Gmail server",
        description="Compare your local archive with what's on the Gmail server.",
        epilog="""
Shows:
  - Emails on Gmail but not downloaded locally
  - Emails downloaded locally but deleted from Gmail

Examples:
  ownmail sync-check              Quick summary
  ownmail sync-check --verbose    Show all differences
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sync_check_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full list of differences instead of truncated",
    )

    # db-check command
    db_check_parser = subparsers.add_parser(
        "db-check",
        help="Check database integrity and fix issues",
        description="Check the database for integrity issues and optionally fix them.",
        epilog="""
Checks for:
  - Duplicate FTS entries (fixable with --fix)
  - Orphaned FTS entries (fixable with --fix)
  - Missing FTS entries (run 'reindex' to fix)
  - Hash mismatches (run 'reindex' to fix)

Examples:
  ownmail db-check              Check only, report issues
  ownmail db-check --fix        Check and fix what can be fixed
  ownmail db-check -v           Show detailed issue list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    db_check_parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix fixable issues (duplicate FTS entries, orphaned entries)",
    )
    db_check_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed list of issues",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config file
    config = load_config(args.config)

    # Determine archive_dir: CLI arg > config file > default
    if args.archive_dir:
        archive_dir = args.archive_dir
    elif "archive_dir" in config:
        archive_dir = Path(config["archive_dir"])
    else:
        archive_dir = DEFAULT_ARCHIVE_DIR

    try:
        archive = GmailArchive(archive_dir, config)

        if args.command == "setup":
            archive.cmd_setup(args.credentials_file)
        elif args.command == "backup":
            archive.cmd_backup()
        elif args.command == "search":
            archive.cmd_search(args.query)
        elif args.command == "stats":
            archive.cmd_stats()
        elif args.command == "reindex":
            archive.cmd_reindex(
                file_path=args.file,
                pattern=args.pattern,
                force=args.force,
                debug=args.debug
            )
        elif args.command == "add-labels":
            archive.cmd_add_labels()
        elif args.command == "verify":
            archive.cmd_verify(verbose=args.verbose)
        elif args.command == "rehash":
            archive.cmd_rehash()
        elif args.command == "sync-check":
            archive.cmd_sync_check(verbose=args.verbose)
        elif args.command == "db-check":
            archive.cmd_db_check(fix=args.fix, verbose=args.verbose)

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
