"""Local label routes exercise durable archive writes without provider access."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from ownmail.web import create_app


@pytest.fixture
def label_client(tmp_path, sample_eml_simple):
    archive = EmailArchive(tmp_path, {})
    provider = MagicMock(account="test@example.com", source_name="test")
    provider.get_new_message_ids.return_value = (["message"], "cursor")
    provider.download_message.return_value = (sample_eml_simple, ["Original"])
    assert archive.backup(provider)["success_count"] == 1
    email_id = ArchiveDatabase.make_email_id(provider.account, "message")
    path = tmp_path / archive.db.get_email_by_id(email_id)[1]
    client = create_app(archive).test_client()
    return client, archive, email_id, path


@pytest.mark.parametrize("labels", [["New", "Receipts, 2026", " Work "], [], ["INBOX", "DRAFT", "Unread"]])
def test_label_edit_route_preserves_owned_bytes_and_other_metadata(label_client, labels):
    client, archive, email_id, path = label_client
    original = path.read_bytes()
    sidecar.write_metadata(path, {"version": 1, "labels": ["Original"], "extra": {"retained": True}})
    with (
        patch("ownmail.providers.gmail.GmailProvider", side_effect=AssertionError("Unexpected server access")),
        patch("ownmail.providers.imap.ImapProvider", side_effect=AssertionError("Unexpected server access")),
    ):
        response = client.post(f"/labels/{email_id}", json={"labels": labels})
    assert response.status_code == 200
    assert response.json == {"indexed": True}
    assert client.get(f"/labels/{email_id}").json == {"labels": labels}
    assert sidecar.read_metadata(path) == {"version": 1, "labels": labels, "extra": {"retained": True}}
    assert set(archive.db.get_labels_for_email(email_id)) == set(labels)
    assert path.read_bytes() == original
    assert "Original" not in archive.db.get_label_counts()
    if "New" in labels:
        assert archive.db.get_label_counts()["New"] == 1
        assert archive.db.search('label:"New"')[0][0] == email_id


def test_index_failure_returns_saved_outcome_and_retry_repairs_search(label_client):
    client, archive, email_id, path = label_client
    with patch.object(archive.db, "set_labels_for_email", side_effect=sqlite3.OperationalError("locked")):
        response = client.post(f"/labels/{email_id}", json={"labels": []})
    assert response.status_code == 200
    assert response.json == {"indexed": False}
    assert sidecar.read_labels(path) == []
    assert client.get(f"/labels/{email_id}").json == {"labels": []}
    assert archive.db.get_labels_for_email(email_id) == ["Original"]

    assert client.post(f"/labels/{email_id}", json={"labels": []}).json == {"indexed": True}
    assert archive.db.get_labels_for_email(email_id) == []


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"labels": None}, {"labels": [""]}, {"labels": [1]}, {"labels": ["UNREAD"]}]
)
def test_invalid_label_payload_does_not_write(label_client, payload):
    client, archive, email_id, path = label_client
    original = sidecar.sidecar_path(path).read_bytes()
    response = client.post(f"/labels/{email_id}", json=payload)
    assert response.status_code == 400
    assert response.json["error"]
    assert sidecar.sidecar_path(path).read_bytes() == original
    assert archive.db.get_labels_for_email(email_id) == ["Original"]


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_message_has_no_local_label_edit_target(label_client, method):
    client, archive, email_id, path = label_client
    response = getattr(client, method)("/labels/active-only", json={"labels": ["New"]})
    assert response.status_code == 404
    assert sidecar.read_labels(path) == ["Original"]
    assert archive.db.get_labels_for_email(email_id) == ["Original"]


def test_unreadable_sidecar_is_reported_without_overwriting_it(label_client):
    client, _, email_id, path = label_client
    sidecar.sidecar_path(path).write_text("{broken")
    assert client.get(f"/labels/{email_id}").status_code == 400
    assert client.post(f"/labels/{email_id}", json={"labels": ["New"]}).status_code == 400
    assert sidecar.sidecar_path(path).read_text() == "{broken"


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("error", [OSError("private path"), sqlite3.OperationalError("database details")])
def test_label_io_failures_return_a_message_without_internal_details(label_client, method, error):
    client, archive, email_id, _ = label_client
    operation = "get_local_labels" if method == "get" else "set_local_labels"
    with patch.object(archive, operation, side_effect=error):
        response = getattr(client, method)(f"/labels/{email_id}", json={"labels": ["New"]})
    assert response.status_code == 503
    assert response.json == {"error": "Labels could not be read or saved. Please try again."}


def test_cross_origin_label_edit_is_rejected(label_client):
    client, archive, email_id, path = label_client
    response = client.post(
        f"/labels/{email_id}", json={"labels": ["New"]}, headers={"Origin": "https://external.example"}
    )
    assert response.status_code == 403
    assert sidecar.read_labels(path) == ["Original"]
    assert archive.db.get_labels_for_email(email_id) == ["Original"]
