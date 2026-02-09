#!/usr/bin/env python3
"""
Gmail Archive

A comprehensive tool for backing up and searching Gmail emails.
All credentials are stored securely in macOS Keychain.

Commands:
    setup    - Configure OAuth credentials (one-time setup)
    backup   - Download new emails from Gmail
    search   - Full-text search across downloaded emails
    stats    - Show backup statistics
    reindex  - Rebuild the search index

First-time Setup:
1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable the Gmail API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON
6. Run: python gmail_archive.py setup
7. Paste the JSON contents when prompted
8. Delete the downloaded JSON file

Usage:
    python gmail_archive.py setup
    python gmail_archive.py setup --credentials-file ~/Downloads/credentials.json
    python gmail_archive.py backup [--archive-dir PATH]
    python gmail_archive.py search "query" [--archive-dir PATH]
    python gmail_archive.py stats [--archive-dir PATH]
    python gmail_archive.py reindex [--archive-dir PATH]
"""

import os
import sys
import json
import base64
import sqlite3
import hashlib
import email
import argparse
import re
import signal
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from email.policy import default as email_policy

# Optional YAML support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Third-party imports
try:
    import keyring
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError as e:
    print(f"Missing required package: {e}")
    print("\nPlease install required packages:")
    print("    pip install google-auth google-auth-oauthlib google-api-python-client keyring")
    sys.exit(1)

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
DEFAULT_ARCHIVE_DIR = SCRIPT_DIR / "archive"
DEFAULT_CONFIG_FILENAME = "config.yaml"
KEYCHAIN_SERVICE = "gmail-archive"
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
            
            with open(path, "r") as f:
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
            raise ValueError(f"Invalid JSON: {e}")
        
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
        self.db_path = archive_dir / "archive.db"
        archive_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Main emails table - minimal metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    message_id TEXT PRIMARY KEY,
                    filename TEXT,
                    downloaded_at TEXT
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

    def mark_downloaded(self, message_id: str, filename: str) -> None:
        """Mark a message as downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO emails 
                (message_id, filename, downloaded_at)
                VALUES (?, ?, ?)
                """,
                (message_id, filename, datetime.now().isoformat()),
            )
            conn.commit()

    def index_email(
        self,
        message_id: str,
        subject: str,
        sender: str,
        recipients: str,
        date_str: str,
        body: str,
        attachments: str,
    ) -> None:
        """Add email to full-text search index."""
        with sqlite3.connect(self.db_path) as conn:
            # Remove existing entry if any
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
            conn.commit()

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
    """Parse .eml files for indexing."""

    @staticmethod
    def parse_file(filepath: Path) -> dict:
        """Parse an .eml file and extract searchable content."""
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email_policy)

        # Extract headers
        subject = msg.get("Subject", "") or ""
        sender = msg.get("From", "") or ""
        
        # Combine all recipient fields
        recipients = []
        for header in ["To", "Cc", "Bcc"]:
            val = msg.get(header, "")
            if val:
                recipients.append(val)
        recipients_str = ", ".join(recipients)
        
        date_str = msg.get("Date", "") or ""
        
        # Extract body text
        body_parts = []
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Get attachment filenames
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
                
                # Extract text content
                if content_type == "text/plain":
                    try:
                        payload = part.get_content()
                        if isinstance(payload, str):
                            body_parts.append(payload)
                    except:
                        pass
                elif content_type == "text/html" and not body_parts:
                    # Only use HTML if no plain text
                    try:
                        payload = part.get_content()
                        if isinstance(payload, str):
                            # Strip HTML tags for indexing
                            text = re.sub(r'<[^>]+>', ' ', payload)
                            text = re.sub(r'\s+', ' ', text)
                            body_parts.append(text)
                    except:
                        pass
        else:
            try:
                payload = msg.get_content()
                if isinstance(payload, str):
                    if msg.get_content_type() == "text/html":
                        payload = re.sub(r'<[^>]+>', ' ', payload)
                        payload = re.sub(r'\s+', ' ', payload)
                    body_parts.append(payload)
            except:
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

    def __init__(self, archive_dir: Path):
        self.archive_dir = archive_dir
        self.emails_dir = archive_dir / "emails"
        self.keychain = KeychainStorage(KEYCHAIN_SERVICE)
        self.db = ArchiveDatabase(archive_dir)
        self.service = None

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
                print("\nRun 'gmail_archive.py setup' first to configure credentials.")
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

    def download_message(self, message_id: str) -> Optional[Path]:
        """Download a single message and save it atomically."""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )

            raw_data = base64.urlsafe_b64decode(message["raw"])
            email_msg = email.message_from_bytes(raw_data)
            date_str = email_msg.get("Date", "")

            try:
                from email.utils import parsedate_to_datetime
                msg_date = parsedate_to_datetime(date_str)
                date_prefix = msg_date.strftime("%Y%m%d_%H%M%S")
                year_month = msg_date.strftime("%Y/%m")
            except:
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

            rel_path = str(filepath.relative_to(self.archive_dir))
            self.db.mark_downloaded(message_id=message_id, filename=rel_path)

            return filepath

        except HttpError as e:
            print(f"\n  Error downloading {message_id}: {e}")
            return None

    def index_email(self, message_id: str, filepath: Path) -> bool:
        """Index an email for full-text search."""
        try:
            parsed = EmailParser.parse_file(filepath)
            self.db.index_email(
                message_id=message_id,
                subject=parsed["subject"],
                sender=parsed["sender"],
                recipients=parsed["recipients"],
                date_str=parsed["date_str"],
                body=parsed["body"],
                attachments=parsed["attachments"],
            )
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
        print("Gmail Archive - Backup")
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

        try:
            for i, msg_id in enumerate(new_message_ids, 1):
                if interrupted:
                    break

                print(f"  [{i}/{len(new_message_ids)}] Downloading and indexing...", end="\r")
                filepath = self.download_message(msg_id)
                if filepath:
                    self.index_email(msg_id, filepath)
                    success_count += 1
                else:
                    error_count += 1
        finally:
            # Restore original signal handler
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

        for msg_id, filename, subject, sender, date_str, snippet in results:
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
        print("Gmail Archive - Statistics")
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
        print("Gmail Archive - Setup")
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
            
            with open(credentials_file, "r") as f:
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
            print("\nYou can now run: gmail_archive.py backup")
            
            # Remind user to delete the source file if imported from file
            if credentials_file:
                print(f"\n⚠ Remember to securely delete: {credentials_file}")
                print(f"  rm {credentials_file}")
        except ValueError as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)

    def cmd_reindex(self) -> None:
        """Rebuild the search index."""
        print("\n" + "=" * 50)
        print("Gmail Archive - Reindex")
        print("=" * 50 + "\n")

        print("Clearing existing index...")
        self.db.clear_index()

        # Get all downloaded emails
        with sqlite3.connect(self.db.db_path) as conn:
            emails = conn.execute(
                "SELECT message_id, filename FROM emails"
            ).fetchall()

        if not emails:
            print("No emails to index.")
            return

        print(f"Indexing {len(emails)} emails...\n")

        success_count = 0
        error_count = 0

        for i, (msg_id, filename) in enumerate(emails, 1):
            print(f"  [{i}/{len(emails)}] Indexing...", end="\r")
            filepath = self.archive_dir / filename
            if filepath.exists():
                if self.index_email(msg_id, filepath):
                    success_count += 1
                else:
                    error_count += 1
            else:
                error_count += 1

        print("\n" + "-" * 50)
        print("Reindex Complete!")
        print(f"  Indexed: {success_count} emails")
        if error_count > 0:
            print(f"  Errors: {error_count}")
        print("-" * 50 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Gmail Archive - Backup and search your Gmail emails",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s setup                           First-time credential setup
  %(prog)s setup --credentials-file creds.json
  %(prog)s backup                          Download new emails
  %(prog)s backup --archive-dir /Volumes/Secure/gmail
  %(prog)s search "invoice from:amazon"   Search emails
  %(prog)s search "subject:meeting"        Search by subject
  %(prog)s stats                           Show statistics
  %(prog)s reindex                         Rebuild search index

Config file:
  Create a config.yaml in the current directory:
  
    archive_dir: /Volumes/My Passport Encrypted/Emails
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
        help=f"Directory to store emails and database",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup command
    setup_parser = subparsers.add_parser("setup", help="Configure OAuth credentials")
    setup_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Path to credentials JSON file (will be imported and can be deleted)",
    )

    # backup command
    subparsers.add_parser("backup", help="Download new emails from Gmail")

    # search command
    search_parser = subparsers.add_parser("search", help="Search archived emails")
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
    subparsers.add_parser("stats", help="Show archive statistics")

    # reindex command
    subparsers.add_parser("reindex", help="Rebuild the search index")

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
        archive = GmailArchive(archive_dir)

        if args.command == "setup":
            archive.cmd_setup(args.credentials_file)
        elif args.command == "backup":
            archive.cmd_backup()
        elif args.command == "search":
            archive.cmd_search(args.query)
        elif args.command == "stats":
            archive.cmd_stats()
        elif args.command == "reindex":
            archive.cmd_reindex()

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
