"""Capture preserves organization while omitting mailbox status."""

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from tests.test_live_imap_batch import provider_for
from tests.test_live_providers import gmail


@pytest.mark.parametrize("protocol", ["gmail_api", "gmail_imap", "imap"])
def test_capture_omits_status_and_preserves_owned_snapshot(tmp_path, protocol):
    archive = EmailArchive(tmp_path / "archive")
    if protocol == "gmail_api":
        provider = gmail(["UNREAD", "STARRED", "IMPORTANT", "Label_1"])
    else:
        provider = provider_for({"Projects": [1]}, gmail=protocol == "gmail_imap")
        provider._conn.flags[1] = r"\Seen \Flagged $Important"
        provider._conn.labels[1] = [r"\Starred", r"\Important", "Projects"]
    first = archive.backup(provider, active_downloads=True)
    assert first["active_complete"] and first["success_count"] == 1
    (path,) = archive.archive_dir.rglob("*.eml")
    assert sidecar.read_labels(path) == ["Projects"]
    # A local edit and any older captured status labels remain owned metadata.
    metadata = sidecar.read_metadata(path)
    metadata["labels"] = ["Locally filed", "STARRED", "IMPORTANT"]
    sidecar.write_metadata(path, metadata)
    before = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()
    if protocol == "gmail_api":
        provider._service.users().messages().get().execute.return_value["labelIds"] = ["Label_1"]
    else:
        provider._conn.flags.clear()
        provider._conn.labels[1] = ["Projects"]
    second = archive.backup(provider, active_downloads=True)
    assert second["success_count"] == 0
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before


@pytest.mark.parametrize("gmail_imap", [False, True])
@pytest.mark.parametrize("mode", ["fallback", "dedup", "gmail_lookup"])
def test_imap_download_label_paths_omit_advertised_status_views(gmail_imap, mode):
    provider = provider_for({"Suivis": [1], "Prioritaires": [1], "Starred": [1]}, gmail=gmail_imap)
    provider._conn.attributes = {"Suivis": r"\Flagged", "Prioritaires": r"\Important"}
    assert set(provider._list_folders()) == {"Suivis", "Prioritaires", "Starred"}
    if mode == "dedup":
        provider._folder_lookup = {"Suivis:1": ["Suivis", "Prioritaires", "Starred"]}
    elif mode == "gmail_lookup":
        provider._message_id_to_folders = {"<one@example.test>": ["Prioritaires", "Starred"]}
    labels = provider._get_labels_for_downloaded("Suivis:1", b"Message-ID: <one@example.test>\r\n\r\nBody", "Suivis")
    assert labels == ([] if mode == "fallback" else ["Starred"])


@pytest.mark.parametrize("gmail_imap", [False, True])
def test_live_status_views_preserve_scope_and_real_folder_names(gmail_imap):
    provider = provider_for({"Suivis": [1], "Starred": [2]}, gmail=gmail_imap, active_exclude_folders=["Suivis"])
    provider._conn.attributes = {"Suivis": r"\Flagged"}
    provider._conn.flags[1] = r"\Draft"
    provider._conn.labels = {1: [r"\Starred", "Suivis", "Starred"], 2: ["Starred"]}
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    first, second = snapshot.messages
    assert first.state == "active" and not first.active_allowed
    assert "Suivis" in first.active_scope
    assert first.labels == (("Starred",) if gmail_imap else ())
    assert second.labels == ("Starred",)
    fresh = provider.read_live_message(first.message_id)
    assert fresh.labels == first.labels and not fresh.active_allowed
