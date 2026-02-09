"""Maintenance commands for ownmail.

This module contains commands for archive maintenance:
- reindex: Rebuild the full-text search index
- verify: Verify archive integrity (files, hashes, database)
- sync_check: Compare local archive with server
- update_labels: Update labels from server or derive from IMAP folders
"""

import hashlib
import signal
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from ownmail.parser import EmailParser


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

        # Find email_id for this file
        rel_path = None
        try:
            rel_path = file_path.relative_to(archive.archive_dir)
        except ValueError:
            # file_path might be absolute from different base
            pass

        if rel_path:
            with sqlite3.connect(db_path) as conn:
                result = conn.execute(
                    "SELECT email_id FROM emails WHERE filename = ?",
                    (str(rel_path),)
                ).fetchone()
                if result:
                    email_id = result[0]
                    print(f"Indexing: {file_path.name}")
                    if _index_single_email(archive, email_id, file_path, debug):
                        print("✓ Indexed successfully")
                    else:
                        print("✗ Failed to index")
                    return

        # If not in DB, use filename as email_id
        print(f"Indexing: {file_path.name}")
        if _index_single_email(archive, file_path.stem, file_path, debug):
            print("✓ Indexed successfully")
        else:
            print("✗ Failed to index")
        return

    # Build the pattern for matching
    like_pattern = None
    if pattern:
        like_pattern = "%" + pattern.replace("*", "%").replace("?", "_") + "%"

    # Get emails to index
    t0 = time.time()
    print("Finding emails to index...", end="", flush=True)
    with sqlite3.connect(db_path) as conn:
        if like_pattern:
            if force:
                # Force mode: select ALL matching emails regardless of indexed state
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE filename LIKE ?""",
                    (like_pattern,)
                ).fetchall()
                print(f" {len(emails)} matching '{pattern}' (force) ({time.time()-t0:.1f}s)")
            else:
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE filename LIKE ?
                       AND (indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash)""",
                    (like_pattern,)
                ).fetchall()
                total_matching = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE filename LIKE ?",
                    (like_pattern,)
                ).fetchone()[0]
                print(f" {len(emails)} of {total_matching} matching '{pattern}' ({time.time()-t0:.1f}s)")
        else:
            if force:
                # Force mode: select ALL emails
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails"""
                ).fetchall()
                print(f" {len(emails)} emails (force) ({time.time()-t0:.1f}s)")
            else:
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                   FROM emails
                   WHERE indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash"""
            ).fetchall()
            total_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            already_indexed = total_emails - len(emails)
            print(f" {len(emails)} emails ({time.time()-t0:.1f}s)")
            if already_indexed > 0:
                print(f"  (skipping {already_indexed} already-indexed)")

    if not emails:
        print("\nAll emails are already indexed. Use --force to reindex everything.")
        return

    # For full reindex with force mode, rebuild FTS table from scratch
    # This is necessary because contentless FTS5 can't delete without original content
    if force and not pattern and not file_path:
        print("Rebuilding FTS index...", end="", flush=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS emails_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE emails_fts USING fts5(
                    subject,
                    sender,
                    recipients,
                    body,
                    attachments,
                    content='',
                    tokenize='porter unicode61'
                )
            """)
            # Also clear indexed_hash so all emails get reindexed
            conn.execute("UPDATE emails SET indexed_hash = NULL, subject = NULL")
            conn.commit()
        print(" done")

    print(f"\nIndexing {len(emails)} emails...")
    print("(Press Ctrl-C to pause - progress is saved, run again to resume)\n")

    success_count = 0
    error_count = 0
    interrupted = False
    start_time = time.time()
    last_commit_count = 0
    COMMIT_INTERVAL = 50  # Commit every N emails

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
        for i, (msg_id, filename, _content_hash, _indexed_hash) in enumerate(emails, 1):
            if interrupted:
                break

            filepath = archive.archive_dir / filename
            short_name = Path(filename).name[:40]

            # Show what we're working on
            print(f"\r\033[K  [{i}/{len(emails)}] {short_name}", end="", flush=True)

            if not filepath.exists():
                error_count += 1
                continue

            # Index the email (updates emails table, FTS synced via triggers)
            if _index_email_for_reindex(archive, msg_id, filepath, batch_conn, debug):
                success_count += 1
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
        # Commit any remaining updates
        batch_conn.commit()
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
    email_id: str,
    filepath: Path,
    debug: bool = False,
) -> bool:
    """Index a single email file."""
    try:
        parsed = EmailParser.parse_file(filepath=filepath)
        archive.db.index_email(
            email_id=email_id,
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
    email_id: str,
    filepath: Path,
    conn: sqlite3.Connection,
    debug: bool = False,
) -> bool:
    """Index email during reindex (uses batch connection)."""
    try:
        # Read file once for both parsing and hashing
        with open(filepath, "rb") as f:
            content = f.read()

        content_hash = hashlib.sha256(content).hexdigest()
        parsed = EmailParser.parse_file(content=content)

        # Create snippet from body
        body = parsed["body"]
        snippet = body[:200] + "..." if len(body) > 200 else body

        # Preserve existing labels from email_labels table
        existing_labels_rows = conn.execute(
            "SELECT el.label FROM email_labels el JOIN emails e ON e.rowid = el.email_rowid WHERE e.email_id = ?",
            (email_id,)
        ).fetchall()
        labels_list = [row[0] for row in existing_labels_rows]
        recipients = parsed["recipients"]

        # recipient_emails normalized table is populated below

        # Check if has attachments
        attachments = parsed["attachments"]
        has_attachments = 1 if attachments else 0

        # Update metadata in emails table and get rowid in one query
        row = conn.execute(
            """
            UPDATE emails SET
                subject = ?,
                sender = ?,
                recipients = ?,
                date_str = ?,
                snippet = ?,
                indexed_hash = ?,
                content_hash = COALESCE(content_hash, ?),
                has_attachments = ?
            WHERE email_id = ?
            RETURNING rowid
            """,
            (parsed["subject"], parsed["sender"], recipients,
             parsed["date_str"], snippet,
             content_hash, content_hash, has_attachments, email_id)
        ).fetchone()

        # Insert into FTS and normalized tables
        if row:
            rowid = row[0]

            conn.execute(
                """
                INSERT INTO emails_fts (rowid, subject, sender, recipients, body, attachments)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rowid, parsed["subject"], parsed["sender"], recipients,
                 parsed["body"], attachments)
            )

            # Populate email_recipients normalized table
            conn.execute("DELETE FROM email_recipients WHERE email_rowid = ?", (rowid,))
            if recipients:
                normalized = ArchiveDatabase._normalize_recipients(recipients)
                for email_addr in normalized.strip(',').split(','):
                    email_addr = email_addr.strip()
                    if email_addr:
                        conn.execute(
                            "INSERT OR IGNORE INTO email_recipients (email_rowid, recipient_email) VALUES (?, ?)",
                            (rowid, email_addr)
                        )

            # Populate email_labels normalized table
            # Get email_date from emails table for the covering index
            email_date_row = conn.execute(
                "SELECT email_date FROM emails WHERE rowid = ?", (rowid,)
            ).fetchone()
            email_date = email_date_row[0] if email_date_row else None

            conn.execute("DELETE FROM email_labels WHERE email_rowid = ?", (rowid,))
            if labels_list:
                for label in labels_list:
                    label = label.strip()
                    if label:
                        conn.execute(
                            "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                            (rowid, label, email_date)
                        )

        return True
    except Exception as e:
        if debug:
            print(f"\n  Error indexing {filepath}: {e}")
        return False


def _verify_single_file(args: tuple) -> tuple:
    """Verify a single file's hash. Returns (status, filename).

    Status: 'ok', 'missing', 'corrupted', 'no_hash'
    """
    archive_dir, filename, stored_hash = args

    filepath = archive_dir / filename

    if not filepath.exists():
        return ('missing', filename)

    if not stored_hash:
        return ('no_hash', filename)

    # Compute current hash
    with open(filepath, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()

    if current_hash == stored_hash:
        return ('ok', filename)
    else:
        return ('corrupted', filename)


def cmd_verify(archive: EmailArchive, fix: bool = False, verbose: bool = False) -> None:
    """Verify archive integrity: files, hashes, and database health.

    Checks:
    - File integrity (missing files, hash mismatches)
    - Moved/renamed files (missing + orphaned with matching hash)
    - Orphaned files (on disk but not indexed)
    - Database health (missing metadata, FTS sync, stale hashes)

    With --fix:
    - Updates DB paths for moved/renamed files
    - Removes DB rows for files that no longer exist on disk
    - Rebuilds FTS index when out of sync
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print("\n" + "=" * 50)
    print("ownmail - Verify")
    print("=" * 50 + "\n")

    total_start = time.time()
    issues_found = 0
    issues_fixed = 0

    db_path = archive.db.db_path

    # ── Phase 1: File integrity ──────────────────────────────────────────

    with sqlite3.connect(db_path) as conn:
        emails = conn.execute(
            "SELECT email_id, filename, content_hash FROM emails"
        ).fetchall()

    total = len(emails)
    ok_count = 0
    missing_count = 0
    corrupted_count = 0
    no_hash_count = 0
    corrupted_files = []
    missing_files = []
    missing_email_ids = []
    missing_hashes = {}  # content_hash -> (filename, email_id)
    indexed_files = set()

    if total == 0:
        print("No emails in database.\n")
    else:
        print(f"1. Verifying {total} files...\n")

        work_items = []
        email_id_by_filename = {}
        hash_by_filename = {}
        for email_id, filename, stored_hash in emails:
            indexed_files.add(filename)
            email_id_by_filename[filename] = email_id
            hash_by_filename[filename] = stored_hash
            work_items.append((archive.archive_dir, filename, stored_hash))

        completed = 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(_verify_single_file, item): item for item in work_items}

            for future in as_completed(futures):
                completed += 1
                print(f"  [{completed}/{total}] Verifying...\033[K", end="\r")

                status, filename = future.result()
                if status == 'ok':
                    ok_count += 1
                elif status == 'missing':
                    missing_count += 1
                    missing_files.append(filename)
                    eid = email_id_by_filename[filename]
                    missing_email_ids.append(eid)
                    stored_hash = hash_by_filename[filename]
                    if stored_hash:
                        missing_hashes[stored_hash] = (filename, eid)
                elif status == 'corrupted':
                    corrupted_count += 1
                    corrupted_files.append(filename)
                elif status == 'no_hash':
                    no_hash_count += 1

        # Orphaned files
        print("\n  Scanning for orphaned files...\033[K", end="\r")
        orphaned_files = []
        for subdir in ["emails", "sources"]:
            check_dir = archive.archive_dir / subdir
            if check_dir.exists():
                for eml_file in check_dir.rglob("*.eml"):
                    rel_path = str(eml_file.relative_to(archive.archive_dir))
                    if rel_path not in indexed_files:
                        orphaned_files.append(rel_path)

        # Detect moved/renamed files by matching hashes
        moved_files = []  # (old_path, new_path, email_id)
        if missing_hashes and orphaned_files:
            remaining_orphans = []
            for orphan_path in orphaned_files:
                orphan_full = archive.archive_dir / orphan_path
                try:
                    with open(orphan_full, "rb") as f:
                        orphan_hash = hashlib.sha256(f.read()).hexdigest()
                except OSError:
                    remaining_orphans.append(orphan_path)
                    continue

                if orphan_hash in missing_hashes:
                    old_path, eid = missing_hashes.pop(orphan_hash)
                    moved_files.append((old_path, orphan_path, eid))
                    missing_files.remove(old_path)
                    missing_email_ids.remove(eid)
                    missing_count -= 1
                else:
                    remaining_orphans.append(orphan_path)
            orphaned_files = remaining_orphans

        # Report file results
        print(f"\n  ✓ OK: {ok_count}")
        if no_hash_count > 0:
            issues_found += 1
            print(f"  ? No hash stored: {no_hash_count}")
        if moved_files:
            issues_found += 1
            moved_labels = [f"{old} → {new}" for old, new, _ in moved_files]
            _print_file_list(moved_labels, "⟳ Moved/renamed", verbose)
            if fix:
                with sqlite3.connect(db_path) as conn:
                    for _old_path, new_path, eid in moved_files:
                        conn.execute(
                            "UPDATE emails SET filename = ? WHERE email_id = ?",
                            (new_path, eid),
                        )
                    conn.commit()
                issues_fixed += 1
                print(f"    → Updated {len(moved_files)} DB paths")
        if missing_count > 0:
            issues_found += 1
            _print_file_list(missing_files, "✗ Missing from disk", verbose)
            if fix:
                with sqlite3.connect(db_path) as conn:
                    # Collect affected accounts before deleting
                    affected_accounts = set()
                    for eid in missing_email_ids:
                        row = conn.execute(
                            "SELECT account FROM emails WHERE email_id = ?", (eid,)
                        ).fetchone()
                        if row and row[0]:
                            affected_accounts.add(row[0])
                        conn.execute("DELETE FROM emails WHERE email_id = ?", (eid,))
                    # Also reset sync state in the same transaction
                    for account in affected_accounts:
                        conn.execute(
                            "DELETE FROM sync_state WHERE key LIKE ?",
                            (f"{account}/%",),
                        )
                    conn.commit()
                issues_fixed += 1
                print(f"    → Removed {missing_count} stale DB entries")
                if affected_accounts:
                    # Verify sync state was actually cleared
                    with sqlite3.connect(db_path) as verify_conn:
                        for account in affected_accounts:
                            remaining = verify_conn.execute(
                                "SELECT COUNT(*) FROM sync_state WHERE key LIKE ?",
                                (f"{account}/%",),
                            ).fetchone()[0]
                            if remaining > 0:
                                # Force delete with a fresh connection
                                verify_conn.execute(
                                    "DELETE FROM sync_state WHERE key LIKE ?",
                                    (f"{account}/%",),
                                )
                                verify_conn.commit()
                    print(f"    → Reset sync state for {len(affected_accounts)} account(s) (next backup will do a full sync)")
        if len(orphaned_files) > 0:
            issues_found += 1
            _print_file_list(orphaned_files, "? On disk but not indexed", verbose)
        if corrupted_count > 0:
            issues_found += 1
            _print_file_list(corrupted_files, "✗ CORRUPTED (hash mismatch)", verbose)

    # ── Phase 2: Database health ─────────────────────────────────────────

    print("\n2. Checking database...\n")

    with sqlite3.connect(db_path) as conn:
        # Missing metadata
        missing_metadata = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE subject IS NULL"
        ).fetchone()[0]

        if missing_metadata > 0:
            issues_found += 1
            print(f"  ✗ {missing_metadata} emails missing metadata (not indexed)")
        else:
            print("  ✓ All emails have metadata")

        # FTS sync
        fts_count = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        emails_with_metadata = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE subject IS NOT NULL"
        ).fetchone()[0]

        if fts_count != emails_with_metadata:
            issues_found += 1
            print(f"  ✗ FTS out of sync ({fts_count} vs {emails_with_metadata} indexed)")
            if fix:
                conn.execute("DROP TABLE IF EXISTS emails_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE emails_fts USING fts5(
                        subject, sender, recipients, body, attachments,
                        content='', tokenize='porter unicode61'
                    )
                """)
                conn.execute("""
                    INSERT INTO emails_fts(rowid, subject, sender, recipients, body, attachments)
                    SELECT rowid, COALESCE(subject, ''), COALESCE(sender, ''),
                           COALESCE(recipients, ''), '', ''
                    FROM emails WHERE subject IS NOT NULL
                """)
                conn.commit()
                issues_fixed += 1
                print("    → FTS rebuilt (run 'reindex --force' to restore body text)")
        else:
            print(f"  ✓ FTS in sync ({fts_count} entries)")

        # Hash mismatches (indexed_hash vs content_hash)
        hash_mismatches = conn.execute("""
            SELECT COUNT(*) FROM emails
            WHERE content_hash IS NOT NULL
              AND indexed_hash IS NOT NULL
              AND content_hash != indexed_hash
        """).fetchone()[0]

        if hash_mismatches > 0:
            issues_found += 1
            print(f"  ✗ {hash_mismatches} emails with stale index")
        else:
            print("  ✓ All indexed emails up to date")

        # Missing hashes
        null_content_hash = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE content_hash IS NULL"
        ).fetchone()[0]

        if null_content_hash > 0:
            issues_found += 1
            print(f"  ? {null_content_hash} emails without content hash")
        else:
            print("  ✓ All emails have hashes")

        # Duplicate content (same content_hash, different email_id)
        dup_rows = conn.execute("""
            SELECT content_hash, COUNT(*) as cnt
            FROM emails
            WHERE content_hash IS NOT NULL
            GROUP BY content_hash
            HAVING cnt > 1
        """).fetchall()
        dup_count = sum(cnt - 1 for _, cnt in dup_rows)

        if dup_count > 0:
            issues_found += 1
            print(f"  ✗ {dup_count} duplicate emails ({len(dup_rows)} unique messages duplicated)")
            if verbose:
                for content_hash, _cnt in dup_rows[:10]:
                    rows = conn.execute(
                        "SELECT email_id, provider_id, filename FROM emails WHERE content_hash = ?",
                        (content_hash,)
                    ).fetchall()
                    for eid, pid, fn in rows:
                        print(f"      {eid} | {pid} | {fn}")
                if len(dup_rows) > 10:
                    print(f"      ... and {len(dup_rows) - 10} more groups")
            if fix:
                removed_count = 0
                removed_files = 0
                for content_hash, _cnt in dup_rows:
                    # Get all rows for this content_hash, keep the one with highest rowid (newest)
                    rows = conn.execute(
                        "SELECT rowid, email_id, filename FROM emails WHERE content_hash = ? ORDER BY rowid DESC",
                        (content_hash,)
                    ).fetchall()
                    # Keep the first (newest), delete the rest
                    for rowid, _email_id, filename in rows[1:]:
                        # Delete labels
                        conn.execute(
                            "DELETE FROM email_labels WHERE email_rowid = ?", (rowid,)
                        )
                        # Delete recipients
                        conn.execute(
                            "DELETE FROM email_recipients WHERE email_rowid = ?", (rowid,)
                        )
                        # Delete the email row
                        conn.execute(
                            "DELETE FROM emails WHERE rowid = ?", (rowid,)
                        )
                        # Delete the orphaned .eml file
                        eml_path = archive.archive_dir / filename
                        if eml_path.exists():
                            eml_path.unlink()
                            removed_files += 1
                        removed_count += 1
                # Rebuild FTS since we can't delete from contentless FTS5
                conn.execute("DROP TABLE IF EXISTS emails_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE emails_fts USING fts5(
                        subject, sender, recipients, body, attachments,
                        content='', tokenize='porter unicode61'
                    )
                """)
                conn.execute("""
                    INSERT INTO emails_fts(rowid, subject, sender, recipients, body, attachments)
                    SELECT rowid, COALESCE(subject, ''), COALESCE(sender, ''),
                           COALESCE(recipients, ''), '', ''
                    FROM emails WHERE subject IS NOT NULL
                """)
                conn.commit()
                issues_fixed += 1
                print(f"    → Removed {removed_count} duplicate DB entries and {removed_files} orphaned files")
                print("    → FTS rebuilt (run 'reindex --force' to restore body text)")
        else:
            print("  ✓ No duplicate emails")

    # ── Summary ──────────────────────────────────────────────────────────

    total_time = time.time() - total_start

    print("\n" + "-" * 50)
    if issues_found == 0:
        print("All checks passed!")
        print(f"  ✓ {ok_count} files verified, database healthy")
    else:
        print(f"Verify complete — {issues_found} issue(s) found")
        if fix:
            fixed_remaining = issues_found - issues_fixed
            if issues_fixed > 0:
                print(f"  Fixed: {issues_fixed}")
            if fixed_remaining > 0:
                print(f"  Remaining: {fixed_remaining}")
                # Actionable suggestions for unfixed issues
                suggestions = []
                if moved_files:
                    suggestions.append("  • 'ownmail verify --fix' to update paths for moved files")
                if missing_metadata > 0 or hash_mismatches > 0:
                    suggestions.append("  • 'ownmail reindex' to populate metadata / update stale index")
                if len(orphaned_files) > 0:
                    suggestions.append("  • 'ownmail reindex' to index orphaned files")
                if corrupted_count > 0:
                    suggestions.append("  • Delete corrupted files, then 'ownmail backup' to re-download")
                if dup_count > 0:
                    suggestions.append("  • 'ownmail verify --fix' to remove duplicate emails")
                for s in suggestions:
                    print(s)
        else:
            # Suggestions for all issues
            suggestions = []
            if moved_files:
                suggestions.append("  • 'ownmail verify --fix' to update paths for moved files")
            if missing_count > 0:
                suggestions.append("  • 'ownmail verify --fix' to remove stale DB entries for missing files")
            if len(orphaned_files) > 0:
                suggestions.append("  • 'ownmail reindex' to index orphaned files")
            if corrupted_count > 0:
                suggestions.append("  • Delete corrupted files, then 'ownmail backup' to re-download")
            if missing_metadata > 0 or hash_mismatches > 0:
                suggestions.append("  • 'ownmail reindex' to populate metadata / update stale index")
            if fts_count != emails_with_metadata:
                suggestions.append("  • 'ownmail verify --fix' to rebuild FTS index")
            if dup_count > 0:
                suggestions.append("  • 'ownmail verify --fix' to remove duplicate emails")
            if suggestions:
                print("\n  To fix:")
                for s in suggestions:
                    print(s)

    print(f"\n  Time: {total_time:.1f}s")
    print("-" * 50 + "\n")


def cmd_sync_check(
    archive: EmailArchive,
    source_name: str = None,
    verbose: bool = False,
) -> None:
    """Compare local archive with server.

    Supports both Gmail API and IMAP sources. When no --source is specified,
    checks the first configured source.
    """
    print("\n" + "=" * 50)
    print("ownmail - Sync Check")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Find the source to check
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        source = sources[0]

    source_type = source.get("type")
    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Create and authenticate provider
    if source_type == "gmail_api":
        from ownmail.providers.gmail import GmailProvider

        provider = GmailProvider(
            account=account,
            keychain=archive.keychain,
            source_name=source["name"],
        )
    elif source_type == "imap":
        from ownmail.providers.imap import ImapProvider

        provider = ImapProvider(
            account=account,
            keychain=archive.keychain,
            host=source.get("host", "imap.gmail.com"),
            port=source.get("port", 993),
            exclude_folders=source.get("exclude_folders"),
            source_name=source["name"],
        )
    else:
        print(f"❌ sync-check is not supported for source type '{source_type}'")
        return

    provider.authenticate()

    # Get all message IDs from server
    print("Fetching message IDs from server...")
    server_ids = set(provider.get_all_message_ids())

    # Close IMAP connection if applicable
    if hasattr(provider, "close"):
        provider.close()

    # Get all local message IDs for this account
    local_ids = archive.db.get_downloaded_ids(account)

    print(f"\nServer: {len(server_ids)} emails")
    print(f"Local:  {len(local_ids)} emails\n")

    # Find differences
    on_server_not_local = server_ids - local_ids
    on_local_not_server = local_ids - server_ids
    in_sync = server_ids & local_ids

    print("-" * 50)
    print("Sync Check Complete!")
    print(f"  ✓ In sync: {len(in_sync)}")

    # Display differences
    if on_server_not_local:
        print(f"  ↓ On server but not local: {len(on_server_not_local)}")
        show_count = len(on_server_not_local) if verbose else min(len(on_server_not_local), 5)
        for msg_id in list(on_server_not_local)[:show_count]:
            print(f"      {msg_id}")
        if not verbose and len(on_server_not_local) > 5:
            print(f"      ... and {len(on_server_not_local) - 5} more (use --verbose to show all)")
        print("\n  Run 'backup' to download these emails.")

    if on_local_not_server:
        # Get filenames for these
        with sqlite3.connect(archive.db.db_path) as conn:
            local_only_files = []
            for msg_id in on_local_not_server:
                result = conn.execute(
                    "SELECT filename FROM emails WHERE provider_id = ? AND account = ?", (msg_id, account)
                ).fetchone()
                if result:
                    local_only_files.append(f"{result[0]} ({msg_id})")
                else:
                    local_only_files.append(msg_id)

        print(f"  ✗ On local but not on server (deleted from server?): {len(on_local_not_server)}")
        show_count = len(local_only_files) if verbose else min(len(local_only_files), 5)
        for f in local_only_files[:show_count]:
            print(f"      {f}")
        if not verbose and len(local_only_files) > 5:
            print(f"      ... and {len(local_only_files) - 5} more (use --verbose to show all)")

    if not on_server_not_local and not on_local_not_server:
        print("\n  ✓ Local archive is fully in sync with server!")
    print("-" * 50 + "\n")


def cmd_update_labels(archive: EmailArchive, source_name: str = None) -> None:
    """Fetch/derive labels and update the database.

    For Gmail API: fetches labels from server via API.
    For IMAP: derives labels from IMAP folder names (stored in provider_id).

    Labels are stored in the database only, not injected into .eml files.
    This keeps .eml files as pure RFC 5322 email as received from the server.
    """
    print("\n" + "=" * 50)
    print("ownmail - Update Labels")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Find the source to update
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        # Use the first source (any type)
        source = sources[0]

    source_type = source.get("type")
    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Get all downloaded emails for this account that don't have labels yet
    with sqlite3.connect(archive.db.db_path) as conn:
        emails = conn.execute(
            """SELECT e.email_id, e.provider_id FROM emails e
               WHERE (e.account = ? OR e.account IS NULL)
               AND NOT EXISTS (
                   SELECT 1 FROM email_labels el WHERE el.email_rowid = e.rowid
               )""",
            (account,)
        ).fetchall()

    if not emails:
        print("No emails need labels.")
        return

    if source_type == "gmail_api":
        _update_labels_gmail(archive, account, emails)
    elif source_type == "imap":
        _update_labels_imap(archive, account, emails)
    else:
        print(f"update-labels is not supported for source type '{source_type}'")


def _update_labels_imap(
    archive: EmailArchive, account: str, emails: list
) -> None:
    """Update labels for IMAP emails by extracting folder from provider_id.

    IMAP provider_id format is "folder:uid", so the folder name IS the label.
    No IMAP connection needed — this is a purely offline operation.
    """
    print(f"Deriving labels from IMAP folder names for {len(emails)} emails...")

    success_count = 0
    skip_count = 0

    with sqlite3.connect(archive.db.db_path) as conn:
        for email_id, provider_id in emails:
            if ":" not in provider_id:
                skip_count += 1
                continue

            folder = provider_id.rsplit(":", 1)[0]
            if not folder:
                skip_count += 1
                continue

            row = conn.execute(
                "SELECT rowid, email_date FROM emails WHERE email_id = ?",
                (email_id,),
            ).fetchone()
            if not row:
                skip_count += 1
                continue
            rowid, email_date = row

            conn.execute(
                "DELETE FROM email_labels WHERE email_rowid = ?", (rowid,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, folder, email_date),
            )

            success_count += 1

    print("\n" + "-" * 50)
    print("Update Labels Complete!")
    print(f"  Updated: {success_count} emails")
    if skip_count > 0:
        print(f"  Skipped: {skip_count}")
    print("-" * 50 + "\n")


def _update_labels_gmail(
    archive: EmailArchive, account: str, emails: list
) -> None:
    """Update labels for Gmail API emails by fetching from server."""
    from ownmail.providers.gmail import GmailProvider

    print(f"Fetching labels for {len(emails)} emails...")
    print("(Press Ctrl-C to stop - progress is saved)\n")

    # Create and authenticate provider
    provider = GmailProvider(account=account, keychain=archive.keychain)
    provider.authenticate()

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
        with sqlite3.connect(archive.db.db_path) as conn:
            for i, (email_id, provider_id) in enumerate(emails, 1):
                if interrupted:
                    break

                print(f"  [{i}/{len(emails)}] Fetching labels...\033[K", end="\r")

                try:
                    labels = provider.get_labels_for_message(provider_id)
                    if not labels:
                        skip_count += 1
                        continue

                    row = conn.execute(
                        "SELECT rowid, email_date FROM emails WHERE email_id = ?",
                        (email_id,),
                    ).fetchone()
                    if not row:
                        skip_count += 1
                        continue
                    rowid, email_date = row

                    conn.execute(
                        "DELETE FROM email_labels WHERE email_rowid = ?",
                        (rowid,),
                    )
                    for label in labels:
                        conn.execute(
                            "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                            (rowid, label, email_date),
                        )

                    success_count += 1

                    # Commit periodically
                    if success_count % 50 == 0:
                        conn.commit()

                except Exception as e:
                    print(f"\n  Error processing {provider_id}: {e}")
                    error_count += 1

    finally:
        signal.signal(signal.SIGINT, original_handler)

    print("\n" + "-" * 50)
    if interrupted:
        print("Update Labels Paused!")
    else:
        print("Update Labels Complete!")
    print(f"  Updated: {success_count} emails")
    print(f"  Skipped (no labels): {skip_count}")
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


def cmd_list_unknown(
    archive: EmailArchive,
    verbose: bool = False,
) -> None:
    """List emails in the unknown/ folder (emails with unparseable dates).

    These emails couldn't have their date extracted during backup, so they
    were placed in the unknown/ folder. Use this command to identify them
    for manual inspection or reprocessing.

    Args:
        archive: EmailArchive instance
        verbose: Show full file paths and additional details
    """
    print("\n" + "=" * 50)
    print("ownmail - Unknown Emails")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    with sqlite3.connect(db_path) as conn:
        results = conn.execute(
            """
            SELECT email_id, filename, account
            FROM emails
            WHERE email_date IS NULL
            ORDER BY account, filename
            """
        ).fetchall()

    if not results:
        print("✓ No emails with unparseable dates")
        return

    print(f"Found {len(results)} emails with unparseable dates:\n")

    # Group by account
    by_account = {}
    for email_id, filename, account in results:
        account = account or "(legacy)"
        if account not in by_account:
            by_account[account] = []
        by_account[account].append((email_id, filename))

    for account, emails in sorted(by_account.items()):
        print(f"  {account}: {len(emails)} emails")
        if verbose:
            for _email_id, filename in emails:
                print(f"    - {filename}")
                # Try to extract date from email file
                filepath = archive.archive_dir / filename
                if filepath.exists():
                    try:
                        import email
                        with open(filepath, "rb") as f:
                            msg = email.message_from_binary_file(f)
                        date_header = msg.get("Date", "")
                        subject = msg.get("Subject", "")[:50]
                        print(f"      Date header: {date_header}")
                        print(f"      Subject: {subject}...")
                    except Exception as e:
                        print(f"      Error reading: {e}")
        print()

    print("-" * 50)
    print("These emails have unparseable Date headers.")
    print("They are excluded from search results by default.")
    print("To include them, use: search --include-unknown")
    print("-" * 50 + "\n")


def cmd_populate_dates(
    archive: EmailArchive,
    verbose: bool = False,
) -> None:
    """Populate email_date column for emails that don't have it set.

    This extracts the date from each email file and stores it in the database
    for faster date-based filtering and sorting.

    Args:
        archive: EmailArchive instance
        verbose: Show progress for each email
    """
    import email
    import email.utils
    import signal
    from concurrent.futures import ThreadPoolExecutor

    print("\n" + "=" * 50)
    print("ownmail - Populate Email Dates")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    with sqlite3.connect(db_path) as conn:
        # Find emails without email_date
        results = conn.execute(
            """
            SELECT email_id, filename
            FROM emails
            WHERE email_date IS NULL
            """
        ).fetchall()

    if not results:
        print("✓ All emails already have dates populated")
        return

    print(f"Found {len(results)} emails without dates\n")
    print("Press Ctrl-C to stop (progress will be saved)\n")

    # Flag for graceful shutdown
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            print("\n\nForce quit...")
            raise SystemExit(1)
        shutdown_requested = True
        print("\n\n⏸ Stopping after current batch...")

    # Install signal handler
    old_handler = signal.signal(signal.SIGINT, signal_handler)

    def extract_date(email_id: str, filename: str) -> tuple:
        """Extract date from a single email file. Returns (email_date, email_id, error)."""
        import re
        from datetime import datetime, timedelta, timezone

        filepath = archive.archive_dir / filename
        email_date = None
        error = None

        if filepath.exists():
            try:
                with open(filepath, "rb") as f:
                    # Read just headers (first 16KB should be enough)
                    content = f.read(16384)
                msg = email.message_from_bytes(content)
                date_header = msg.get("Date", "")
                # Convert Header object to string if needed
                date_str = str(date_header) if date_header else ""

                parsed = None

                # Try standard parsing first
                if date_str:
                    try:
                        parsed = email.utils.parsedate_to_datetime(date_str)
                    except Exception:
                        pass

                # Try ISO format (e.g., "2022-10-16 00:01:52.776975+00:00")
                if not parsed and date_str:
                    try:
                        # Remove microseconds if present
                        iso_str = re.sub(r"\.\d+", "", date_str)
                        parsed = datetime.fromisoformat(iso_str)
                    except Exception:
                        pass

                # Try extracting from malformed date with Korean/garbled weekday
                # Pattern: "XX, DD M YYYY HH:MM:SS +ZZZZ"
                if not parsed and date_str:
                    match = re.search(
                        r"(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([+-]?\d{1,4})?",
                        date_str
                    )
                    if match:
                        try:
                            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            hour, minute, second = int(match.group(4)), int(match.group(5)), int(match.group(6))
                            # Handle 2-digit year
                            if year < 100:
                                year += 2000 if year < 50 else 1900
                            tz_str = match.group(7) or "+0000"
                            # Parse timezone offset
                            if len(tz_str) <= 2:
                                tz_hours = int(tz_str)
                                tz_offset = timezone(timedelta(hours=tz_hours))
                            else:
                                tz_hours = int(tz_str[:-2]) if len(tz_str) > 2 else int(tz_str)
                                tz_mins = int(tz_str[-2:]) if len(tz_str) > 2 else 0
                                from datetime import timedelta
                                tz_offset = timezone(timedelta(hours=tz_hours, minutes=tz_mins))
                            parsed = datetime(year, month, day, hour, minute, second, tzinfo=tz_offset)
                        except Exception:
                            pass

                # Fallback: try first Received header
                if not parsed:
                    received_header = msg.get("Received", "")
                    received = str(received_header) if received_header else ""
                    if received:
                        # Extract date from end of Received header
                        # Format: "... ; Sat, 15 Oct 2022 17:01:54 -0700 (PDT)"
                        match = re.search(r";\s*(.+)$", received)
                        if match:
                            try:
                                parsed = email.utils.parsedate_to_datetime(match.group(1).strip())
                            except Exception:
                                pass

                if parsed:
                    # Normalize to UTC for consistent sorting
                    from datetime import timezone as _tz
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone(_tz.utc)
                    else:
                        parsed = parsed.replace(tzinfo=_tz.utc)
                    email_date = parsed.strftime("%Y-%m-%dT%H:%M:%S+00:00")

            except Exception as e:
                error = str(e)
        else:
            error = "File not found"

        return (email_date, email_id, error)

    success_count = 0
    error_count = 0
    null_count = 0
    batch_size = 100  # Process in smaller chunks for responsiveness
    total = len(results)
    processed = 0

    try:
        # Process in batches so we can check shutdown flag between batches
        with sqlite3.connect(db_path) as conn:
            for batch_start in range(0, total, batch_size):
                if shutdown_requested:
                    break

                batch = results[batch_start:batch_start + batch_size]
                updates = []

                # Use ThreadPoolExecutor for parallel I/O within each batch
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(extract_date, email_id, filename)
                        for email_id, filename in batch
                    ]

                    for future in futures:
                        if shutdown_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break

                        email_date, email_id, error = future.result()
                        processed += 1

                        if error:
                            if verbose:
                                print(f"    Error: {error}")
                            error_count += 1

                        updates.append((email_date, email_id))

                        if email_date:
                            success_count += 1
                        else:
                            null_count += 1

                # Commit this batch
                if updates:
                    conn.executemany(
                        "UPDATE emails SET email_date = ? WHERE email_id = ?",
                        updates
                    )
                    conn.commit()

                # Progress update
                print(f"  [{processed}/{total}] Processing...")

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, old_handler)

    print("\n" + "-" * 50)
    if shutdown_requested:
        print("Populate Dates Paused!")
        print(f"  Processed: {processed} emails")
        print(f"  Remaining: {total - processed} emails")
        print("\n  Run 'populate-dates' again to resume.")
    else:
        print("Populate Dates Complete!")
        print(f"  Updated with date: {success_count} emails")
        print(f"  No parseable date: {null_count} emails")
        if error_count > 0:
            print(f"  Errors: {error_count}")
    print("-" * 50 + "\n")
