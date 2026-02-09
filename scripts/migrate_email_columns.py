#!/usr/bin/env python3
"""Migrate emails table to add sender_email, recipient_emails columns and email_recipients table."""
import re
import sqlite3

db_path = "/Volumes/My Passport Encrypted/ownmail/ownmail.db"


def extract_email(sender_str):
    """Extract email from 'Name <email>' or just 'email'"""
    if not sender_str:
        return None
    # Try to extract from angle brackets
    match = re.search(r'<([^>]+)>', sender_str)
    if match:
        return match.group(1).lower().strip()
    # If no brackets, check if it's just an email
    if '@' in sender_str:
        return sender_str.lower().strip()
    return None


def normalize_recipients(recipients_str):
    """Convert 'a@b.com, Name <c@d.com>' to ',a@b.com,c@d.com,' for exact matching.

    Returns tuple of (normalized_string, list_of_emails)
    """
    if not recipients_str:
        return None, []
    emails = []
    for part in recipients_str.split(','):
        part = part.strip()
        if not part:
            continue
        # Try to extract from angle brackets first
        match = re.search(r'<([^>]+)>', part)
        if match:
            email = match.group(1).lower().strip()
        elif '@' in part:
            email = part.lower().strip()
        else:
            continue
        if email:
            emails.append(email)
    if emails:
        return ',' + ','.join(emails) + ',', emails
    return None, []


def main():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create email_recipients table if it doesn't exist
    print("Creating email_recipients table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_recipients (
            email_rowid INTEGER,
            recipient_email TEXT,
            PRIMARY KEY (email_rowid, recipient_email)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_recipients_email ON email_recipients(recipient_email)")
    conn.commit()

    # Clear existing data for fresh migration
    print("Clearing existing email_recipients data...")
    cur.execute("DELETE FROM email_recipients")
    conn.commit()

    # Reset columns to re-process all
    print("Resetting email columns...")
    cur.execute("UPDATE emails SET sender_email = NULL, recipient_emails = NULL")
    conn.commit()

    # Get count
    total = cur.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    print(f"Processing {total} emails...")

    # Process in batches
    batch_size = 5000
    processed = 0

    while True:
        rows = cur.execute(
            "SELECT rowid, message_id, sender, recipients FROM emails WHERE sender_email IS NULL LIMIT ?",
            (batch_size,)
        ).fetchall()

        if not rows:
            break

        updates = []
        recipient_inserts = []
        for rowid, msg_id, sender, recipients in rows:
            sender_email = extract_email(sender)
            recipient_emails_str, recipient_emails_list = normalize_recipients(recipients)
            # Use empty string instead of NULL to avoid re-processing
            updates.append((sender_email or '', recipient_emails_str or '', msg_id))

            # Build recipient inserts for normalized table
            for email in recipient_emails_list:
                recipient_inserts.append((rowid, email))

        cur.executemany(
            "UPDATE emails SET sender_email = ?, recipient_emails = ? WHERE message_id = ?",
            updates
        )
        cur.executemany(
            "INSERT OR IGNORE INTO email_recipients (email_rowid, recipient_email) VALUES (?, ?)",
            recipient_inserts
        )
        conn.commit()

        processed += len(rows)
        print(f"Processed {processed}/{total}...")

    print("Done!")
    conn.close()


if __name__ == "__main__":
    main()
