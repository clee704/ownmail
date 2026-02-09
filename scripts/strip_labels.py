"""Strip X-Gmail-Labels headers from .eml files and update DB hashes."""

import hashlib
import re
import sqlite3
from pathlib import Path

archive_root = Path("/Volumes/Vault/90 Archive/Emails")
db_path = archive_root / "ownmail.db"

# Pattern to match X-Gmail-Labels header line (handles CRLF and LF)
label_re = re.compile(rb"X-Gmail-Labels:[^\r\n]*\r?\n")

stripped = 0
skipped = 0
errors = 0
hash_updates = []

for eml in archive_root.rglob("*.eml"):
    try:
        data = eml.read_bytes()
        # Only check the header portion (before double newline)
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = data.find(b"\n\n")
        if header_end == -1:
            skipped += 1
            continue

        header = data[:header_end]
        if b"X-Gmail-Labels" not in header:
            skipped += 1
            continue

        # Strip the header
        new_data = label_re.sub(b"", data, count=1)
        eml.write_bytes(new_data)

        # Compute new content hash
        new_hash = hashlib.sha256(new_data).hexdigest()
        rel_path = str(eml.relative_to(archive_root))
        hash_updates.append((new_hash, rel_path))
        stripped += 1
    except Exception as e:
        print(f"Error: {eml}: {e}")
        errors += 1

print(f"Stripped: {stripped}, Skipped: {skipped}, Errors: {errors}")

# Update content_hash and indexed_hash in DB
db = sqlite3.connect(str(db_path))
updated = 0
for new_hash, filename in hash_updates:
    cur = db.execute(
        "UPDATE emails SET content_hash = ?, indexed_hash = ? WHERE filename = ?",
        (new_hash, new_hash, filename),
    )
    updated += cur.rowcount
db.commit()
db.close()
print(f"DB rows updated: {updated}")
