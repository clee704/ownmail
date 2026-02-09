#!/usr/bin/env python3
"""Migrate emails table to add sender_email and recipient_emails columns."""
import sqlite3
import re
import sys

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
    """Convert 'a@b.com, Name <c@d.com>' to ',a@b.com,c@d.com,' for exact matching"""
    if not recipients_str:
        return None
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
        return ',' + ','.join(emails) + ','
    return None


def main():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Reset columns to re-process all
    print("Resetting columns...")
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
            "SELECT message_id, sender, recipients FROM emails WHERE sender_email IS NULL LIMIT ?",
            (batch_size,)
        ).fetchall()

        if not rows:
            break

        updates = []
        for msg_id, sender, recipients in rows:
            sender_email = extract_email(sender)
            recipient_emails = normalize_recipients(recipients)
            updates.append((sender_email, recipient_emails, msg_id))

        cur.executemany(
            "UPDATE emails SET sender_email = ?, recipient_emails = ? WHERE message_id = ?",
            updates
        )
        conn.commit()

        processed += len(rows)
        print(f"Processed {processed}/{total}...")

    print("Done!")
    conn.close()


if __name__ == "__main__":
    main()
