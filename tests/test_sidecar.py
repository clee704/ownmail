"""Tests for per-email label sidecar files."""

import json

import pytest

from ownmail import sidecar


class TestSidecarPath:
    def test_sidecar_path_swaps_extension(self, temp_dir):
        eml = temp_dir / "20240101_120000_abcdef123456.eml"
        assert sidecar.sidecar_path(eml) == temp_dir / "20240101_120000_abcdef123456.json"


class TestReadLabels:
    def test_read_labels_missing_sidecar_returns_none(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        assert sidecar.read_labels(eml) is None

    def test_read_labels_returns_stored_labels(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, ["INBOX", "IMPORTANT"])
        assert sidecar.read_labels(eml) == ["INBOX", "IMPORTANT"]

    def test_read_labels_empty_list_is_not_none(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, [])
        assert sidecar.read_labels(eml) == []

    def test_read_labels_corrupt_json_returns_none(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.sidecar_path(eml).write_text("{not valid json")
        assert sidecar.read_labels(eml) is None


class TestWriteLabels:
    def test_write_labels_creates_json_sidecar(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, ["INBOX"])

        path = sidecar.sidecar_path(eml)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["labels"] == ["INBOX"]
        assert data["version"] == sidecar.SIDECAR_VERSION

    def test_write_labels_dedups_preserving_order(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, ["INBOX", "IMPORTANT", "INBOX"])
        assert sidecar.read_labels(eml) == ["INBOX", "IMPORTANT"]

    def test_write_labels_overwrites_existing(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, ["INBOX"])
        sidecar.write_labels(eml, ["SENT"])
        assert sidecar.read_labels(eml) == ["SENT"]

    def test_write_labels_no_leftover_temp_files(self, temp_dir):
        eml = temp_dir / "msg.eml"
        eml.write_bytes(b"From: a@b.com\n\nbody")
        sidecar.write_labels(eml, ["INBOX"])
        leftovers = list(temp_dir.glob("*.tmp"))
        assert leftovers == []

    def test_write_labels_creates_parent_dirs(self, temp_dir):
        eml = temp_dir / "2024" / "01" / "msg.eml"
        sidecar.write_labels(eml, ["INBOX"])
        assert sidecar.sidecar_path(eml).exists()


class TestSidecarWriteFailure:
    """Tests for the atomic write path in write_labels."""

    def test_temp_file_is_cleaned_up_on_failure(self, tmp_path):
        """A failed write must not leave a .json.tmp file behind."""
        from unittest.mock import patch

        eml = tmp_path / "mail.eml"
        eml.write_bytes(b"From: a@example.com\n\nbody\n")

        with patch("json.dump", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                sidecar.write_labels(eml, ["Work"])

        assert list(tmp_path.glob("*.json.tmp")) == []
        assert not sidecar.sidecar_path(eml).exists()

    def test_rename_failure_cleans_up_and_raises(self, tmp_path):
        """A failed rename should clean up and propagate the error."""
        from unittest.mock import patch

        eml = tmp_path / "mail.eml"
        eml.write_bytes(b"From: a@example.com\n\nbody\n")

        with patch("os.rename", side_effect=OSError("cross-device link")):
            with pytest.raises(OSError, match="cross-device link"):
                sidecar.write_labels(eml, ["Work"])

        assert list(tmp_path.glob("*.json.tmp")) == []

    def test_labels_are_deduplicated_preserving_order(self, tmp_path):
        """Duplicate labels should collapse, keeping first-seen order."""
        eml = tmp_path / "mail.eml"
        eml.write_bytes(b"From: a@example.com\n\nbody\n")

        sidecar.write_labels(eml, ["Work", "Personal", "Work", "Archive", "Personal"])

        assert sidecar.read_labels(eml) == ["Work", "Personal", "Archive"]
