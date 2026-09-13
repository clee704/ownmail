#!/usr/bin/env python3
"""Repair SENT labels contaminated by the historical header-insertion bug.

Dry-run by default. Stop other archive writers before applying a repair.
Only exact folded-References evidence in a hash-verified email qualifies.
Email files are never changed. Private backups contain original metadata.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ownmail import sidecar


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _signature(raw: bytes) -> str | None:
    lines = raw.split(b"\n")
    first = lines[0].rstrip(b"\r")
    if not first.lower().startswith(b"references:"):
        return None
    continuations = []
    for line in lines[1:]:
        if not line.startswith((b" ", b"\t")):
            break
        continuations.append(line.strip())
    try:
        suffix = _normalize(b" ".join(continuations).decode("ascii"))
    except UnicodeDecodeError:
        return None
    if not re.fullmatch(r"<[^<>\s]+@[^<>\s]+>(?: <[^<>\s]+@[^<>\s]+>)*", suffix):
        return None
    return "SENT " + suffix


def _correct(labels: list[str], signature: str) -> list[str]:
    if signature not in labels:
        return labels
    result = []
    for label in labels:
        replacement = "SENT" if label == signature else label
        if replacement != "SENT" or "SENT" not in result:
            result.append(replacement)
    return result


def _candidate(labels: list[str]) -> bool:
    return any(_normalize(label).startswith("SENT <") for label in labels)


def _read_source(path: Path) -> tuple[bytes | None, dict | None]:
    if path.is_symlink():
        raise ValueError("symlink sidecar")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("labels"), list)
        or any(not isinstance(label, str) for label in data["labels"])
    ):
        raise ValueError("invalid sidecar labels")
    return raw, data


def _journal(backup_dir: Path, row: sqlite3.Row, label_rows: list, original: bytes | None, labels: list[str]) -> None:
    identity = {key: row[key] for key in row.keys()}
    document = {
        "version": 1,
        "email": identity,
        "email_labels": [dict(item) for item in label_rows],
        "sidecar_base64": None if original is None else base64.b64encode(original).decode("ascii"),
        "repaired_labels": labels,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup_dir.is_symlink() or backup_dir.stat().st_mode & 0o077:
        raise ValueError("backup directory must be private (mode 0700) and not a symlink")
    path = backup_dir / f"{key}.json"
    fd, temp_path = tempfile.mkstemp(dir=backup_dir, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            if path.is_symlink():
                raise ValueError("symlink backup") from None
            previous = json.loads(path.read_bytes())
            if previous["email"] != identity or set(previous["repaired_labels"]) != set(labels):
                raise ValueError("conflicting backup") from None
        directory_fd = os.open(backup_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temp_path)


def repair(archive: Path, database: Path, *, apply: bool = False, backup_dir: Path | None = None) -> dict[str, int]:
    """Inspect existing metadata and repair only proven historical contamination."""
    if apply and backup_dir is None:
        raise ValueError("--apply requires --backup-dir")
    archive = archive.resolve(strict=True)
    database = database.resolve(strict=True)
    counts = {"scanned": 0, "matched": 0, "repaired": 0, "index_only": 0, "skipped": 0}
    mode = "rw" if apply else "ro"
    with sqlite3.connect(database.as_uri() + f"?mode={mode}", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT rowid, email_id, filename, content_hash, email_date, labels FROM emails")
        for row in rows:
            counts["scanned"] += 1
            try:
                label_rows = conn.execute(
                    "SELECT email_rowid, label, email_date FROM email_labels WHERE email_rowid = ? ORDER BY label",
                    (row["rowid"],),
                ).fetchall()
                indexed = [item["label"] for item in label_rows]
                filename = Path(row["filename"])
                if filename.is_absolute() or ".." in filename.parts or filename.suffix != ".eml":
                    raise ValueError("invalid archive path")
                eml = archive / filename
                if eml.is_symlink() or not eml.resolve(strict=True).is_relative_to(archive):
                    raise ValueError("unsafe archive path")
                source_path = sidecar.sidecar_path(eml)
                original, metadata = _read_source(source_path)
                source = metadata["labels"] if metadata is not None else indexed
                if not _candidate(source) and not _candidate(indexed):
                    continue
                raw = eml.read_bytes()
                if not row["content_hash"] or hashlib.sha256(raw).hexdigest() != row["content_hash"]:
                    raise ValueError("email hash mismatch")
                signature = _signature(raw)
                if signature is None:
                    raise ValueError("no matching header evidence")
                repaired = _correct(source, signature)
                source_changed = repaired != source
                if not source_changed:
                    fixed_index = _correct(indexed, signature)
                    if fixed_index == indexed or set(source) != set(fixed_index):
                        raise ValueError("no matching label evidence")
                    counts["index_only"] += 1
                counts["matched"] += 1
                if not apply:
                    continue
                # The sidecar commits first so a retry can finish the derived index.
                conn.execute("BEGIN IMMEDIATE")
                try:
                    current = conn.execute(
                        "SELECT rowid, email_id, filename, content_hash, email_date, labels FROM emails WHERE rowid = ?",
                        (row["rowid"],),
                    ).fetchone()
                    current_labels = conn.execute(
                        "SELECT email_rowid, label, email_date FROM email_labels WHERE email_rowid = ? ORDER BY label",
                        (row["rowid"],),
                    ).fetchall()
                    if current != row or current_labels != label_rows or _read_source(source_path)[0] != original:
                        raise ValueError("metadata changed during inspection")
                    if hashlib.sha256(eml.read_bytes()).hexdigest() != row["content_hash"]:
                        raise ValueError("email changed during inspection")
                    _journal(backup_dir, row, label_rows, original, repaired)
                    if source_changed:
                        updated = dict(metadata) if metadata is not None else {"version": sidecar.SIDECAR_VERSION}
                        updated["labels"] = repaired
                        sidecar.write_metadata(eml, updated)
                    conn.execute("DELETE FROM email_labels WHERE email_rowid = ?", (row["rowid"],))
                    conn.executemany(
                        "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                        [(row["rowid"], label, row["email_date"]) for label in repaired],
                    )
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
                counts["repaired"] += 1
            except (OSError, ValueError, TypeError, KeyError):
                counts["skipped"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    """Run a dry run or an explicitly requested repair with private backups."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--database", type=Path, help="Defaults to ARCHIVE/ownmail.db")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args(argv)
    if args.apply and args.backup_dir is None:
        parser.error("--apply requires --backup-dir")
    try:
        counts = repair(
            args.archive,
            args.database or args.archive / "ownmail.db",
            apply=args.apply,
            backup_dir=args.backup_dir,
        )
    except KeyboardInterrupt:
        print("Interrupted. Completed repairs are saved; rerun with the same backup directory.")
        return 130
    except (OSError, ValueError, sqlite3.Error):
        print("Repair stopped. Check archive, existing database, and private backup directory.", file=sys.stderr)
        return 1
    print(("Applied: " if args.apply else "Dry run: ") + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
