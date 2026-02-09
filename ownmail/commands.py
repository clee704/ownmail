"""Maintenance commands for ownmail.

This module contains commands for archive maintenance:
- reindex: Rebuild the full-text search index
- verify: Verify file integrity against stored hashes
- rehash: Compute hashes for emails without them
- sync_check: Compare local archive with server
- db_check: Check database integrity
- add_labels: Add Gmail labels to existing emails
"""

import hashlib
import os
import signal
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser
from ownmail.providers.gmail import GmailProvider


def cmd_reindex(
    archive: EmailArchive,
    file_path: Optional[Path] = None,
    pattern: Optional[str] = None,
    force: bool = False,
    debug: bool = False,
) -> None:
    """Rebuild the search index.

    By default, only indexes emails that have changed (content_hash != indexed_hash).
    This makes reindex resumable - if cancelled, just run again to continue.

    Args:
        archive: EmailArchive instance
        file_path: Index only this specific file
        pattern: Index only files matching this glob pattern (e.g., "2024/09/*")
        force: If True, reindex all emails regardless of indexed_hash
        debug: If True, show timing info for each email
    """
    print("\n" + "=" * 50)
    print("ownmail - Reindex")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    # Single file mode
    if file_path:
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return

        # Find message_id for this file
        rel_path = None
        try:
            rel_path = file_path.relative_to(archive.archive_dir)
        except ValueError:
            # file_path might be absolute from different base
            pass

        if rel_path:
            with sqlite3.connect(db_path) as conn:
                result = conn.execute(
                    "SELECT message_id FROM emails WHERE filename = ?",
                    (str(rel_path),)
                ).fetchone()
                if result:
                    msg_id = result[0]
                    print(f"Indexing: {file_path.name}")
                    if _index_single_email(archive, msg_id, file_path, debug):
                        print("✓ Indexed successfully")
                    else:
                        print("✗ Failed to index")
                    return

        # If not in DB, use filename as message_id
        print(f"Indexing: {file_path.name}")
        if _index_single_email(archive, file_path.stem, file_path, debug):
            print("✓ Indexed successfully")
        else:
            print("✗ Failed to index")
        return

    # Force mode: clear indexed_hash so all emails are re-indexed
    if force:
        print("Force mode: will reindex all emails")
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = NULL")
            conn.commit()

    # Get emails to index (where indexed_hash != content_hash or either is NULL)
    with sqlite3.connect(db_path) as conn:
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
    successfully_reindexed = []  # Track which re-indexed emails succeeded

    def signal_handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n⏸ Stopping after current email...")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    # Use a shared connection for batching (much faster on slow disks)
    batch_conn = sqlite3.connect(db_path)
    # WAL mode is faster for writes and crash-safe
    batch_conn.execute("PRAGMA journal_mode = WAL")
    batch_conn.execute("PRAGMA synchronous = NORMAL")

    try:
        for i, (msg_id, filename, _content_hash, indexed_hash) in enumerate(emails, 1):
            if interrupted:
                break

            filepath = archive.archive_dir / filename
            short_name = Path(filename).name[:40]

            # Show what we're working on
            print(f"\r\033[K  [{i}/{len(emails)}] {short_name}", end="", flush=True)

            if not filepath.exists():
                error_count += 1
                continue

            # Index the email
            if _index_email_for_reindex(archive, msg_id, filepath, batch_conn, debug):
                success_count += 1
                # Track re-indexed emails that need old FTS entry deleted
                if indexed_hash is not None:
                    successfully_reindexed.append(msg_id)
            else:
                error_count += 1

            # Commit periodically to save progress
            if success_count - last_commit_count >= COMMIT_INTERVAL:
                batch_conn.commit()
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
        batch_conn.commit()

        # Delete old FTS entries for successfully re-indexed emails (batch delete at end)
        if successfully_reindexed:
            print(f"\n  Cleaning up {len(successfully_reindexed)} old FTS entries...", end="", flush=True)
            t0 = time.time()
            # FTS5 creates rowid, old entries have lower rowid than new ones
            # Delete entries where message_id matches but rowid is not the max for that message_id
            for msg_id in successfully_reindexed:
                batch_conn.execute("""
                    DELETE FROM emails_fts WHERE message_id = ? AND rowid < (
                        SELECT MAX(rowid) FROM emails_fts WHERE message_id = ?
                    )
                """, (msg_id, msg_id))
            batch_conn.commit()
            print(f" done ({time.time()-t0:.1f}s)")

        batch_conn.close()
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


def _index_single_email(
    archive: EmailArchive,
    message_id: str,
    filepath: Path,
    debug: bool = False,
) -> bool:
    """Index a single email file."""
    try:
        parsed = EmailParser.parse_file(filepath=filepath)
        archive.db.index_email(
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
        if debug:
            print(f"\n  Error indexing {filepath}: {e}")
        return False


def _index_email_for_reindex(
    archive: EmailArchive,
    message_id: str,
    filepath: Path,
    conn: sqlite3.Connection,
    debug: bool = False,
) -> bool:
    """Index email during reindex (uses batch connection, skips DELETE)."""
    try:
        parsed = EmailParser.parse_file(filepath=filepath)

        # Insert into FTS (skip DELETE, we batch-delete old entries at end)
        conn.execute(
            """
            INSERT INTO emails_fts
            (message_id, subject, sender, recipients, date_str, body, attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, parsed["subject"], parsed["sender"], parsed["recipients"],
             parsed["date_str"], parsed["body"], parsed["attachments"])
        )

        # Compute content hash if missing and update indexed_hash + labels
        with open(filepath, "rb") as f:
            content = f.read()
        content_hash = hashlib.sha256(content).hexdigest()

        conn.execute(
            """
            UPDATE emails
            SET indexed_hash = ?, content_hash = COALESCE(content_hash, ?), labels = ?
            WHERE message_id = ?
            """,
            (content_hash, content_hash, parsed.get("labels", ""), message_id)
        )

        return True
    except Exception as e:
        if debug:
            print(f"\n  Error indexing {filepath}: {e}")
        return False


def cmd_verify(archive: EmailArchive, verbose: bool = False) -> None:
    """Verify integrity of downloaded emails against stored hashes."""
    print("\n" + "=" * 50)
    print("ownmail - Verify Integrity")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    # Get all downloaded emails with hashes
    with sqlite3.connect(db_path) as conn:
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
        filepath = archive.archive_dir / filename

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
    emails_dir = archive.archive_dir / "emails"
    if emails_dir.exists():
        for eml_file in emails_dir.rglob("*.eml"):
            rel_path = str(eml_file.relative_to(archive.archive_dir))
            if rel_path not in indexed_files:
                orphaned_files.append(rel_path)

    print("\n" + "-" * 50)
    print("Verification Complete!")
    print(f"  ✓ OK: {ok_count}")
    if no_hash_count > 0:
        print(f"  ? No hash stored: {no_hash_count} (run 'rehash' to compute)")
    _print_file_list(missing_files, "✗ In index but missing from disk", verbose)
    _print_file_list(orphaned_files, "? On disk but not in index", verbose)
    _print_file_list(corrupted_files, "✗ CORRUPTED (hash mismatch)", verbose)

    if missing_count == 0 and corrupted_count == 0 and len(orphaned_files) == 0 and no_hash_count == 0:
        print("\n  ✓ All files verified successfully!")
    print("-" * 50 + "\n")


def cmd_rehash(archive: EmailArchive) -> None:
    """Compute and store hashes for emails that don't have them."""
    print("\n" + "=" * 50)
    print("ownmail - Compute Hashes")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    # Get emails without hashes
    with sqlite3.connect(db_path) as conn:
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

        filepath = archive.archive_dir / filename

        if not filepath.exists():
            error_count += 1
            continue

        with open(filepath, "rb") as f:
            content_hash = hashlib.sha256(f.read()).hexdigest()

        with sqlite3.connect(db_path) as conn:
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


def cmd_sync_check(
    archive: EmailArchive,
    source_name: str = None,
    verbose: bool = False,
) -> None:
    """Compare local archive with server.

    Note: Currently only supports Gmail. For other providers, this would need
    to be extended.
    """
    print("\n" + "=" * 50)
    print("ownmail - Sync Check")
    print("=" * 50 + "\n")

    # For now, we need a source to sync check
    # In the future, this could iterate over all sources
    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Get the first gmail source (or specified source)
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        # Find first gmail source
        for s in sources:
            if s.get("type") == "gmail_api":
                source = s
                break
        if not source:
            print("No Gmail source configured. sync-check currently only supports Gmail.")
            return

    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Create and authenticate provider
    provider = GmailProvider(account=account, keychain=archive.keychain)
    provider.authenticate()

    # Get all message IDs from Gmail
    print("Fetching message IDs from Gmail...")
    gmail_ids = set(provider.get_all_message_ids())

    # Get all local message IDs for this account
    local_ids = archive.db.get_downloaded_ids(account)

    print(f"\nGmail: {len(gmail_ids)} emails")
    print(f"Local: {len(local_ids)} emails\n")

    # Find differences
    on_gmail_not_local = gmail_ids - local_ids
    on_local_not_gmail = local_ids - gmail_ids
    in_sync = gmail_ids & local_ids

    print("-" * 50)
    print("Sync Check Complete!")
    print(f"  ✓ In sync: {len(in_sync)}")

    # Display differences
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
        with sqlite3.connect(archive.db.db_path) as conn:
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


def cmd_db_check(archive: EmailArchive, fix: bool = False, verbose: bool = False) -> None:
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
    db_path = archive.db.db_path

    with sqlite3.connect(db_path) as conn:
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


def cmd_add_labels(archive: EmailArchive, source_name: str = None) -> None:
    """Add Gmail labels to existing downloaded emails."""
    print("\n" + "=" * 50)
    print("ownmail - Add Labels")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Get the first gmail source (or specified source)
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        for s in sources:
            if s.get("type") == "gmail_api":
                source = s
                break
        if not source:
            print("No Gmail source configured. add-labels only supports Gmail.")
            return

    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Create and authenticate provider
    provider = GmailProvider(account=account, keychain=archive.keychain)
    provider.authenticate()

    # Get all downloaded emails for this account
    with sqlite3.connect(archive.db.db_path) as conn:
        emails = conn.execute(
            "SELECT message_id, filename FROM emails WHERE account = ? OR account IS NULL",
            (account,)
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

            filepath = archive.archive_dir / filename
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
                labels = provider.get_labels_for_message(msg_id)
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
                except Exception:
                    os.close(fd)
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

            except Exception as e:
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


def _print_file_list(files: list, label: str, verbose: bool, max_show: int = 5) -> None:
    """Helper to print a list of files with truncation unless verbose."""
    if not files:
        return
    print(f"  {label}: {len(files)}")
    show_count = len(files) if verbose else min(len(files), max_show)
    for f in files[:show_count]:
        print(f"      {f}")
    if not verbose and len(files) > max_show:
        print(f"      ... and {len(files) - max_show} more (use --verbose to show all)")
