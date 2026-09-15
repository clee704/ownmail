"""Active reading and search preserve the boundary around owned mail."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from lxml import html

from ownmail.archive import EmailArchive
from ownmail.web import create_app
from tests import test_ui_shell
from tests.conftest import mock_archive_db
from tests.test_live_sync import MailServer, message, owned_rows, sync

shell_browser = test_ui_shell.shell_browser


class ActiveWebArchive:
    def __init__(self, root, content):
        self.archive_dir = root / "archive"
        self.archive_dir.mkdir()
        self.cached_file = root / "cache" / "message.eml"
        self.cached_file.parent.mkdir()
        self.cached_file.write_bytes(content)
        self.db = mock_archive_db(get_email_by_id=None)
        self.auto_expire_trash = Mock(return_value=0)
        self.info = {
            "active": True,
            "cache_id": "active-message",
            "archive_id": None,
            "archived": False,
            "source_name": "mail",
            "checked_at": "2026-09-14T12:00:00+00:00",
            "content_at": "2026-09-14T11:59:00+00:00",
            "complete": True,
        }
        self.search = Mock(
            return_value=[
                (
                    "active-message",
                    str(self.cached_file),
                    "Active subject",
                    "Sender <sender@example.com>",
                    "Mon, 14 Sep 2026 10:00:00 +0000",
                    "Live contents",
                    1,
                ),
                (
                    "archived-message",
                    "owned.eml",
                    "Archived subject",
                    "sender@example.com",
                    "Mon, 14 Sep 2026 09:00:00 +0000",
                    "Owned contents",
                    0,
                ),
            ]
        )

    def active_info(self, email_id):
        return self.info if email_id in (self.info["cache_id"], self.info["archive_id"]) else None

    def active_count(self):
        return 1

    def consolidated_count(self):
        return 2

    def get_readable_email(self, email_id):
        if email_id == "active-message":
            return (email_id, str(self.cached_file), None, None, None, None)
        return self.db.get_email_by_id(email_id)


@pytest.fixture
def active_app(tmp_path, sample_eml_multipart):
    archive = ActiveWebArchive(tmp_path, sample_eml_multipart)
    app = create_app(archive, display_timezone="UTC")
    return app, archive


def test_search_shows_active_freshness_and_preserves_archived_rows(active_app):
    app, _ = active_app
    tree = html.fromstring(app.test_client().get("/search").data)
    active, archived = tree.xpath('//ul[@id="ownmail-email-list"]/li')
    assert "ownmail-email-row-active" in active.get("class")
    assert "Active · Checked Sep 14, 2026 12:00 UTC" in active.text_content()
    assert not active.xpath('.//span[contains(@class, "ownmail-label")]')
    assert active.xpath(".//input[@disabled]")
    assert archived.get("class") == "ownmail-email-row"
    assert not archived.xpath(".//input[@disabled]")
    assert "Checked" not in archived.text_content()
    link = active.xpath('.//a[@class="ownmail-email-row-link"]')[0]
    assert link.get("aria-describedby").split() == ["attachment-1", "active-1"]


def test_active_sidebar_count_and_filter_selection(active_app):
    app, archive = active_app
    tree = html.fromstring(app.test_client().get("/search?q=is%3Aactive").data)
    link = tree.xpath('//nav//a[@aria-label="Active"]')[0]
    assert link.get("href") == "/search?q=is%3Aactive"
    assert link.get("aria-current") == "page"
    assert link.xpath('.//span[@class="ownmail-sidebar-badge"]')[0].text == "1"
    assert tree.xpath('//h2[text()="Active"]')
    assert archive.search.call_args.kwargs["sort"] == "date_desc"


@pytest.mark.parametrize("checked", [None, "malformed"])
def test_incomplete_refresh_retains_copy_with_unknown_freshness(active_app, checked):
    app, archive = active_app
    archive.info.update(active=False, complete=False, checked_at=checked, content_at=None)
    listing = html.fromstring(app.test_client().get("/search").data)
    freshness = listing.get_element_by_id("active-1").text_content()
    assert "Server state unconfirmed" in freshness
    assert "Refresh incomplete" in freshness
    assert "unknown" in freshness
    reader = html.fromstring(app.test_client().get("/email/active-message").data)
    notice = reader.xpath('//section[@aria-label="Active message status"]')[0].text_content()
    assert "Refresh incomplete; server state is unconfirmed." in notice
    assert "Contents cached unknown." in notice
    assert "This email has an attachment." in reader.text_content()


def test_cached_reader_has_content_and_no_local_controls(active_app):
    app, _ = active_app
    response = app.test_client().get("/email/active-message")
    assert response.status_code == 200
    tree = html.fromstring(response.data)
    assert "This email has an attachment." in tree.text_content()
    notice = tree.xpath('//section[@aria-label="Active message status"]')[0].text_content()
    assert "Manage this message in your mail client." in notice
    assert "Contents cached Sep 14, 2026 11:59 UTC." in notice
    assert not tree.xpath('//*[@id="ownmail-edit-labels" or @id="ownmail-label-editor"]')
    assert not tree.xpath('//button[@aria-label="Move to trash" or @aria-label="Restore from trash"]')


def test_owned_reader_links_to_active_content_and_keeps_local_controls(active_app):
    app, archive = active_app
    archive.info.update(archived=True, archive_id="owned")
    (archive.archive_dir / "owned.eml").write_text("Subject: Saved subject\n\nSaved body")
    archive.db.get_email_by_id.return_value = ("owned", "owned.eml", None, None, None, None)
    client = app.test_client()
    tree = html.fromstring(client.get("/email/owned").data)
    assert "Saved body" in tree.text_content()
    assert "Also Active on the server" in tree.text_content()
    assert tree.xpath('//section[@aria-label="Active message status"]//a[starts-with(@href, "/email/active-message")]')
    assert tree.xpath('//*[@id="ownmail-edit-labels"]')
    assert tree.xpath('//button[@aria-label="Move to trash"]')
    cached = html.fromstring(client.get("/email/active-message").data)
    assert cached.xpath('//section[@aria-label="Active message status"]//a[starts-with(@href, "/email/owned")]')
    assert not cached.xpath('//*[@id="ownmail-edit-labels"]')


def test_dual_state_label_post_changes_only_the_owned_snapshot(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    original = message(state="eligible", labels=("Saved",))
    provider = MailServer([original])
    assert sync(archive, provider)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    provider.messages[original.message_id] = replace(original, state="active", labels=("INBOX", "Server label"))
    assert sync(archive, provider)["active_refreshed"] == 1
    cache = archive.active_cache()
    cache_id = archive.active_info(email_id)["cache_id"]
    before_cache = cache.get(cache_id)
    before_content = cache.read(cache_id)
    before_server = dict(provider.messages)
    provider.reads.clear()
    client = create_app(archive).test_client()

    response = client.post(f"/labels/{email_id}", json={"labels": ["Local edit"]})

    assert response.status_code == 200
    assert response.json == {"indexed": True}
    assert archive.get_local_labels(email_id) == ["Local edit"]
    assert archive.db.get_labels_for_email(email_id) == ["Local edit"]
    assert (archive.archive_dir / filename).read_bytes() == original.raw
    assert cache.get(cache_id) == before_cache
    assert cache.read(cache_id) == before_content
    assert provider.messages == before_server
    assert provider.reads == []


@pytest.mark.parametrize("route", ["raw", "download", "attachment"])
def test_cached_file_routes_use_external_cache(active_app, route):
    app, archive = active_app
    path = f"/{route}/active-message" + ("/0" if route == "attachment" else "")
    response = app.test_client().get(path)
    assert response.status_code == 200
    if route == "raw":
        assert b"Subject: Email with Attachment" in response.data
    elif route == "download":
        assert response.data == archive.cached_file.read_bytes()
    else:
        assert response.data.startswith(b"%PDF")
        assert response.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"


@pytest.mark.parametrize("route", ["email", "raw", "download", "attachment"])
def test_unowned_external_paths_are_rejected(active_app, route):
    app, archive = active_app
    archive.db.get_email_by_id.return_value = ("outside", str(archive.cached_file), None, None, None, None)
    path = f"/{route}/outside" + ("/0" if route == "attachment" else "")
    assert app.test_client().get(path).status_code == 404


def test_bulk_selection_excludes_cached_messages(active_app, shell_browser):
    app, _ = active_app
    test_ui_shell.run_shell_browser(
        app,
        shell_browser,
        """
const boxes = document.querySelectorAll('.ownmail-email-checkbox input');
const selectAll = byId('ownmail-select-all');
selectAll.click();
assert(!boxes[0].checked);
assert(boxes[1].checked);
assert.equal(byId('ownmail-selected-count').textContent, '1');
assert(selectAll.checked);
""",
        path="/search",
    )
