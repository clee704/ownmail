"""Regression tests for the bounded historical label repair."""

import base64
import hashlib
import json
import sqlite3

import pytest

from ownmail import sidecar
from scripts import repair_labels

BAD_LABEL = "SENT <second@example.com> <third@example.com>"
RAW = (
    b"References: <first@example.com>\n"
    b" <second@example.com>\n"
    b"\t<third@example.com>\n"
    b"From: sender@example.com\n"
    b"Subject: A synthetic message\n\n"
    b"Body preserved byte for byte.\n"
)


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    eml = root / "message.eml"
    eml.write_bytes(RAW)
    db = root / "ownmail.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE emails (
                email_id TEXT PRIMARY KEY, filename TEXT, content_hash TEXT,
                email_date TEXT, labels TEXT
            );
            CREATE TABLE email_labels (
                email_rowid INTEGER, label TEXT, email_date TEXT,
                PRIMARY KEY (email_rowid, label)
            );
        """)
        conn.execute(
            "INSERT INTO emails VALUES (?, ?, ?, ?, ?)",
            ("synthetic-id", eml.name, hashlib.sha256(RAW).hexdigest(), "2020-01-01", "legacy"),
        )
        conn.executemany(
            "INSERT INTO email_labels VALUES (1, ?, '2020-01-01')",
            [(BAD_LABEL,), ("Receipts, taxes",)],
        )
    sidecar.sidecar_path(eml).write_bytes(
        json.dumps({"version": 1, "labels": [BAD_LABEL, "Receipts, taxes"], "extra": {"retained": True}}).encode()
    )
    return root, db, eml, tmp_path / "backup"


def _indexed(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT label, email_date FROM email_labels ORDER BY label").fetchall()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_matches_only_folded_continuations(newline):
    assert repair_labels._signature(RAW.replace(b"\n", newline)) == BAD_LABEL


@pytest.mark.parametrize(
    "raw",
    [
        b"From: a@example.com\n" + RAW,
        RAW.replace(b"\n <second@example.com>\n\t<third@example.com>", b" <second@example.com> <third@example.com>"),
        RAW.replace(b"\t<third@example.com>", b"\tProject notes"),
        RAW.replace(b"<second@example.com>", b"<second>"),
        RAW.replace(b"<second@example.com>", b"<\xff@example.com>"),
    ],
)
def test_rejects_unproven_header_shapes(raw):
    assert repair_labels._signature(raw) is None


def test_dry_run_leaves_all_files_unchanged(archive):
    root, db, eml, backup = archive
    before = {path.name: path.read_bytes() for path in root.iterdir()}

    result = repair_labels.repair(root, db, backup_dir=backup)

    assert result == {"scanned": 1, "matched": 1, "repaired": 0, "index_only": 0, "skipped": 0}
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert not backup.exists()


def test_apply_preserves_eml_extra_metadata_and_exact_other_labels(archive):
    root, db, eml, backup = archive
    original_sidecar = sidecar.sidecar_path(eml).read_bytes()
    old_rows = _indexed(db)

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result == {"scanned": 1, "matched": 1, "repaired": 1, "index_only": 0, "skipped": 0}
    assert eml.read_bytes() == RAW
    assert json.loads(sidecar.sidecar_path(eml).read_bytes()) == {
        "version": 1,
        "labels": ["SENT", "Receipts, taxes"],
        "extra": {"retained": True},
    }
    assert _indexed(db) == [("Receipts, taxes", "2020-01-01"), ("SENT", "2020-01-01")]
    journal_path = next(backup.iterdir())
    journal = json.loads(journal_path.read_bytes())
    assert base64.b64decode(journal["sidecar_base64"]) == original_sidecar
    assert [(item["label"], item["email_date"]) for item in journal["email_labels"]] == old_rows
    assert journal["email"]["email_id"] == "synthetic-id"
    assert journal["email"]["content_hash"] == hashlib.sha256(RAW).hexdigest()
    assert journal_path.stat().st_mode & 0o077 == 0
    assert backup.stat().st_mode & 0o077 == 0

    again = repair_labels.repair(root, db, apply=True, backup_dir=backup)
    assert again["matched"] == 0
    assert again["repaired"] == 0
    assert len(list(backup.iterdir())) == 1


def test_interruption_after_sidecar_write_can_finish_index(archive, monkeypatch):
    root, db, eml, backup = archive
    original_sidecar = sidecar.sidecar_path(eml).read_bytes()
    write_metadata = sidecar.write_metadata

    def interrupt_after_write(*args):
        write_metadata(*args)
        raise KeyboardInterrupt

    monkeypatch.setattr(sidecar, "write_metadata", interrupt_after_write)
    with pytest.raises(KeyboardInterrupt):
        repair_labels.repair(root, db, apply=True, backup_dir=backup)
    assert BAD_LABEL in dict(_indexed(db))
    assert sidecar.read_labels(eml) == ["SENT", "Receipts, taxes"]
    monkeypatch.setattr(sidecar, "write_metadata", write_metadata)

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result == {"scanned": 1, "matched": 1, "repaired": 1, "index_only": 1, "skipped": 0}
    assert BAD_LABEL not in dict(_indexed(db))
    journal = json.loads(next(backup.iterdir()).read_bytes())
    assert base64.b64decode(journal["sidecar_base64"]) == original_sidecar
    assert eml.read_bytes() == RAW


@pytest.mark.parametrize(
    "change", ["hash", "missing_hash", "mismatch", "missing_eml", "escape", "symlink", "corrupt", "types"]
)
def test_rejects_missing_or_changed_evidence(archive, change):
    root, db, eml, backup = archive
    if change == "hash":
        eml.write_bytes(RAW + b"changed")
    elif change == "missing_hash":
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE emails SET content_hash = NULL")
    elif change == "mismatch":
        updated = RAW.replace(b"second@example.com", b"different@example.com")
        eml.write_bytes(updated)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE emails SET content_hash = ?", (hashlib.sha256(updated).hexdigest(),))
    elif change == "missing_eml":
        eml.unlink()
    elif change == "escape":
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE emails SET filename = '../message.eml'")
    elif change == "symlink":
        source_path = sidecar.sidecar_path(eml)
        source_path.rename(root / "original.json")
        source_path.symlink_to(root / "original.json")
    elif change == "corrupt":
        sidecar.sidecar_path(eml).write_text("{broken")
    else:
        sidecar.sidecar_path(eml).write_text('{"labels": [1]}')
    old_rows = _indexed(db)
    before = {path.name: path.read_bytes() for path in root.iterdir()}

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["skipped"] == 1
    assert result["repaired"] == 0
    assert _indexed(db) == old_rows
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert not backup.exists()


def test_missing_sidecar_uses_exact_database_labels(archive):
    root, db, eml, backup = archive
    sidecar.sidecar_path(eml).unlink()

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 1
    assert set(sidecar.read_labels(eml)) == {"SENT", "Receipts, taxes"}
    assert json.loads(next(backup.iterdir()).read_bytes())["sidecar_base64"] is None


def test_legitimate_angle_label_untouched(archive):
    root, db, eml, backup = archive
    labels = ["SENT <project@example.com>", "Notes <draft>", "Receipts, taxes"]
    sidecar.write_labels(eml, labels)

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 0
    assert sidecar.read_labels(eml) == labels
    assert not backup.exists()


def test_sidecar_wins_when_database_has_stale_unrelated_labels(archive):
    root, db, eml, backup = archive
    sidecar.write_labels(eml, [BAD_LABEL, "Source, label"])

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 1
    assert set(dict(_indexed(db))) == {"SENT", "Source, label"}


def test_deduplicates_only_repaired_sent_label(archive):
    root, db, eml, backup = archive
    sidecar.write_metadata(eml, {"version": 1, "labels": [BAD_LABEL, "SENT", "Other", "Other"]})

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 1
    assert sidecar.read_labels(eml) == ["SENT", "Other", "Other"]
    assert set(dict(_indexed(db))) == {"SENT", "Other"}


def test_unmatched_label_with_duplicates_is_not_a_repair(archive):
    root, db, eml, backup = archive
    labels = ["SENT <project@example.com>", "Other", "Other"]
    sidecar.write_metadata(eml, {"version": 1, "labels": labels})

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 0
    assert sidecar.read_labels(eml) == labels
    assert not backup.exists()


def test_interrupted_backup_write_leaves_repair_retryable(archive, monkeypatch):
    root, db, eml, backup = archive
    original = sidecar.sidecar_path(eml).read_bytes()
    dump = json.dump

    def interrupted_dump(value, stream, **kwargs):
        stream.write('{"partial":')
        raise KeyboardInterrupt

    monkeypatch.setattr(json, "dump", interrupted_dump)
    with pytest.raises(KeyboardInterrupt):
        repair_labels.repair(root, db, apply=True, backup_dir=backup)
    assert list(backup.iterdir()) == []
    assert sidecar.sidecar_path(eml).read_bytes() == original
    assert BAD_LABEL in dict(_indexed(db))
    monkeypatch.setattr(json, "dump", dump)

    result = repair_labels.repair(root, db, apply=True, backup_dir=backup)

    assert result["repaired"] == 1
    assert len(list(backup.iterdir())) == 1


def test_cli_requires_backup_for_apply_and_never_initializes_database(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        repair_labels.main(["--archive", str(tmp_path), "--apply"])
    assert caught.value.code == 2
    assert repair_labels.main(["--archive", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []
    assert str(tmp_path) not in capsys.readouterr().out
