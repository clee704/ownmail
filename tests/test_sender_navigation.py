"""Sender navigation prefers stable addresses and preserves name-only senders."""

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import template_rendered
from lxml import html

from ownmail import ArchiveDatabase
from ownmail.query import parse_query
from ownmail.web import create_app, sender_search_url
from tests.conftest import mock_archive_db


def search_query(url):
    params = parse_qs(urlsplit(url).query)
    assert params["sort"] == ["date_desc"]
    return params["q"][0]


def index_message(db, identifier, sender, body="Synthetic message"):
    email_id = db.make_email_id("", identifier)
    db.mark_downloaded(email_id, identifier, identifier + ".eml", email_date="2024-01-01T12:00:00Z")
    db.index_email(email_id, "Synthetic", sender, "reader@example.com", "Mon, 1 Jan 2024", body, "")
    return email_id


def test_sender_address_includes_renamed_sender_and_excludes_same_name(tmp_path):
    db = ArchiveDatabase(tmp_path)
    original = index_message(db, "original", "Alex Sender <shared@example.com>")
    renamed = index_message(db, "renamed", "New Display Name <shared@example.com>")
    index_message(db, "same-name", "Alex Sender <different@example.com>")
    index_message(db, "unrelated", "Someone Else <someone@example.com>", "shared@example.com Alex Sender")
    query = search_query(sender_search_url("Alex Sender", "SHARED@example.com"))
    assert {row[0] for row in db.search(query)} == {original, renamed}


@pytest.mark.parametrize("name", ['Alex "Ops" Lee', "O'Brien", "Ops/Sales", "ACME*", "Team @ Office", "Renée 박"])
def test_name_only_sender_search_handles_quoted_punctuation(tmp_path, name):
    db = ArchiveDatabase(tmp_path)
    matching = index_message(db, "name-only", name)
    index_message(db, "body-only", "Someone Else", name)
    index_message(db, "split-name", "Alex Account", "Ops Lee")
    index_message(db, "prefix-only", "ACMExtra")
    query = search_query(sender_search_url(name, ""))
    assert parse_query(query).error is None
    assert [row[0] for row in db.search(query)] == [matching]


@pytest.mark.parametrize(("name", "address"), [(None, None), ("", ""), ("", "invalid")])
def test_missing_or_unusable_sender_has_no_link(name, address):
    assert sender_search_url(name, address) == ""


def test_invalid_address_falls_back_to_available_name():
    assert search_query(sender_search_url("Alex Sender", "invalid")) == 'from:"Alex Sender"'


@pytest.mark.parametrize("path", ["/search", "/trash", "/email/message"])
@pytest.mark.parametrize(
    ("sender", "expected"),
    [
        ('"Alex \\"Ops\\" Lee" <alex@example.com>', 'from:"alex@example.com"'),
        ('"Alex \\"Ops\\" Lee"', 'from:"Alex ""Ops"" Lee"'),
        ("Alex Sender <invalid>", 'from:"Alex Sender"'),
        ("", None),
    ],
)
def test_list_trash_and_reader_share_sender_rule(tmp_path, path, sender, expected):
    (tmp_path / "message.eml").write_text(
        f"From: {sender}\nTo: reader@example.com\nSubject: Synthetic\n\nSynthetic message.\n"
    )
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.auto_expire_trash.return_value = 0
    archive.db = mock_archive_db()
    archive.db.get_email_by_id.return_value = ("message", "message.eml", None, None, None, None)
    archive.db.get_labels_for_email.return_value = []
    archive.search.return_value = [("message", "message.eml", "Synthetic", sender, "2024-01-01", "Body")]
    archive.db.get_trashed_emails.return_value = [
        ("message", "message.eml", "Synthetic", sender, "2024-01-01", "Body", "2024-01-02", "original.eml")
    ]
    app = create_app(archive)
    contexts = []

    def record(sender, template, context, **extra):
        contexts.append(context)

    with template_rendered.connected_to(record, app):
        response = app.test_client().get(path)
    assert response.status_code == 200
    context = contexts[-1]
    url = context["sender_search_url"] if path.startswith("/email/") else context["results"][0]["sender_search_url"]
    assert (search_query(url) if url else None) == expected
    tree = html.fromstring(response.data)
    if path.startswith("/email/"):
        links = tree.xpath('//span[@class="ownmail-reader-sender"]/a | //dl[@id="ownmail-message-metadata"]/dd[1]/a')
        assert [link.get("href") for link in links] == ([url, url] if url else [])
    else:
        links = tree.xpath('//a[@class="ownmail-email-sender"]')
        assert [link.get("href") for link in links] == ([url] if url else [])
