"""Web download controls, config persistence, and server lifecycle."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from ownmail.web import create_app, run_server
from ownmail.yaml_util import load_yaml
from tests.test_web import mock_archive_db


@pytest.fixture
def archive(tmp_path):
    archive = MagicMock()
    archive.archive_dir = tmp_path / "archive"
    archive.db = mock_archive_db()
    archive.db.get_email_count.return_value = 0
    archive.db.get_trash_count.return_value = 0
    archive.auto_expire_trash.return_value = 0
    return archive


@pytest.fixture
def configured_app(archive, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("# Keep this comment\nsources: []\nweb:\n  page_size: 37\n")
    config.chmod(0o600)
    app = create_app(archive, config_path=str(config))
    yield app, config
    app.extensions["downloads"].stop()


def test_schedule_persists_across_app_restart(configured_app, archive):
    app, config = configured_app
    with app.test_client() as client:
        response = client.post("/downloads/schedule", json={"interval_minutes": 60})
        assert response.status_code == 200
        assert response.json["interval_minutes"] == 60
        assert response.json["next_run"] is not None
        assert client.get("/downloads").headers["Cache-Control"] == "no-store"
    assert "# Keep this comment" in config.read_text()
    assert config.stat().st_mode & 0o777 == 0o600
    assert load_yaml(config) == {"sources": [], "web": {"page_size": 37, "download_interval_minutes": 60}}
    restarted = create_app(archive, config_path=str(config))
    try:
        assert restarted.test_client().get("/downloads").json["interval_minutes"] == 60
        response = restarted.test_client().post("/downloads/schedule", json={"interval_minutes": 0})
        assert response.json["next_run"] is None
        assert load_yaml(config)["web"]["download_interval_minutes"] == 0
    finally:
        restarted.extensions["downloads"].stop()


@pytest.mark.parametrize("value", [None, True, -1, 1, 60.0, "60", [], {}])
def test_invalid_interval_does_not_change_config(configured_app, value):
    app, config = configured_app
    before = config.read_bytes()
    response = app.test_client().post("/downloads/schedule", json={"interval_minutes": value})
    assert response.status_code == 400
    assert config.read_bytes() == before
    assert app.extensions["downloads"].snapshot()["interval_minutes"] == 0


def test_invalid_json_is_rejected(configured_app):
    app, config = configured_app
    before = config.read_bytes()
    client = app.test_client()
    for content in ("[]", "null", "{broken"):
        response = client.post("/downloads/schedule", data=content, content_type="application/json")
        assert response.status_code == 400
    assert config.read_bytes() == before


@pytest.mark.parametrize("operation", ["load_yaml", "save_web_config", "os.replace"])
def test_config_failure_preserves_file_and_schedule(configured_app, operation):
    app, config = configured_app
    before = config.read_bytes()
    with patch(f"ownmail.web_downloads.{operation}", side_effect=OSError("private path")):
        response = app.test_client().post("/downloads/schedule", json={"interval_minutes": 30})
    assert response.status_code == 500
    assert b"private path" not in response.data
    assert config.read_bytes() == before
    assert not list(config.parent.glob(".ownmail-config-*"))
    assert app.extensions["downloads"].snapshot()["interval_minutes"] == 0


@pytest.mark.parametrize("body", ["web: [broken", "web:\n  download_interval_minutes: invalid\n", "web: null\n"])
def test_bad_config_disables_schedule(archive, tmp_path, body):
    config = tmp_path / "config.yaml"
    config.write_text(body)
    app = create_app(archive, config_path=str(config))
    assert app.test_client().get("/downloads").json["interval_minutes"] == 0


def test_no_config_disables_downloads(archive):
    app = create_app(archive)
    client = app.test_client()
    assert client.get("/downloads").json["available"] is False
    assert client.post("/downloads", json={}).status_code == 503
    assert client.post("/downloads/schedule", json={"interval_minutes": 60}).status_code == 503


def test_manual_start_returns_before_child_finishes(configured_app):
    app, _ = configured_app
    process = MagicMock()
    process.poll.return_value = None
    with (
        patch("ownmail.downloads.subprocess.Popen", return_value=process) as spawn,
        patch("ownmail.web._get_server_timezone_name", return_value="UTC"),
    ):
        client = app.test_client()
        started = client.post("/downloads", json={})
        assert started.status_code == 202
        assert started.json["running"] is True
        assert client.post("/downloads", json={}).status_code == 409
        assert client.get("/settings").status_code == 200
        spawn.assert_called_once()
        process.poll.return_value = 0
        assert client.get("/downloads").json["state"] == "succeeded"


def test_spawn_failure_is_visible(configured_app):
    app, _ = configured_app
    with patch("ownmail.downloads.subprocess.Popen", side_effect=OSError("private path")):
        response = app.test_client().post("/downloads", json={})
    assert response.status_code == 503
    assert response.json["state"] == "failed"
    assert b"private path" not in response.data


@pytest.mark.parametrize("endpoint", ["/downloads", "/downloads/schedule"])
def test_download_mutations_reject_cross_origin_and_forms(configured_app, endpoint):
    app, _ = configured_app
    client = app.test_client()
    assert client.post(endpoint, data={"interval_minutes": 0}).status_code == 415
    for headers in (
        {"Origin": "http://attacker.invalid"},
        {"Referer": "http://localhost.attacker.invalid/settings"},
        {"Origin": "null", "Referer": "http://localhost/settings"},
    ):
        assert client.post(endpoint, json={"interval_minutes": 0}, headers=headers).status_code == 403
    response = client.post(
        "/downloads/schedule", json={"interval_minutes": 0}, headers={"Referer": "http://localhost/settings"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "reload,debug,child,starts",
    [
        (False, False, False, True),
        (True, False, False, False),
        (False, True, False, False),
        (True, False, True, True),
        (False, True, True, True),
    ],
)
def test_scheduler_runs_only_in_serving_process(archive, monkeypatch, reload, debug, child, starts):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true" if child else "false")
    manager = MagicMock()
    with (
        patch("ownmail.sanitizer.HtmlSanitizer"),
        patch("ownmail.web_downloads.DownloadManager", return_value=manager),
        patch("flask.Flask.run"),
    ):
        run_server(archive, reload=reload, debug=debug, open_browser=False)
    assert manager.start_scheduler.call_count == int(starts)
    manager.stop.assert_called_once()


def test_server_exception_stops_downloads(archive):
    manager = MagicMock()
    with (
        patch("ownmail.sanitizer.HtmlSanitizer"),
        patch("ownmail.web_downloads.DownloadManager", return_value=manager),
        patch("flask.Flask.run", side_effect=RuntimeError("server failed")),
        pytest.raises(RuntimeError, match="server failed"),
    ):
        run_server(archive, open_browser=False)
    manager.stop.assert_called_once()


@pytest.mark.parametrize("endpoint", ["/settings", "/trust-sender", "/untrust-sender"])
def test_schedule_and_other_config_updates_preserve_each_other(configured_app, endpoint):
    app, config = configured_app
    config.write_text("web:\n  trusted_senders: [old@example.com]\n")
    loaded = Event()
    resume = Event()
    other_started = Event()

    def pause_after_read(path):
        data = load_yaml(path)
        loaded.set()
        assert resume.wait(timeout=5)
        return data

    def request_schedule():
        with app.test_client() as client:
            return client.post("/downloads/schedule", json={"interval_minutes": 60}).status_code

    def request_other():
        with app.test_client() as client:
            other_started.set()
            return client.post(
                endpoint,
                data={
                    "email": "old@example.com" if endpoint == "/untrust-sender" else "new@example.com",
                    "page_size": 42,
                },
            ).status_code

    with patch("ownmail.web_downloads.load_yaml", side_effect=pause_after_read):
        with ThreadPoolExecutor(max_workers=2) as executor:
            schedule = executor.submit(request_schedule)
            try:
                assert loaded.wait(timeout=5)
                other = executor.submit(request_other)
                assert other_started.wait(timeout=5)
                with pytest.raises(TimeoutError):
                    other.result(timeout=0.1)
            finally:
                resume.set()
            assert schedule.result(timeout=5) == 200
            assert other.result(timeout=5) in (200, 302)

    web = load_yaml(config)["web"]
    assert web["download_interval_minutes"] == 60
    if endpoint == "/settings":
        assert web["page_size"] == 42
    elif endpoint == "/trust-sender":
        assert web["trusted_senders"] == ["old@example.com", "new@example.com"]
    else:
        assert web["trusted_senders"] == []


def test_concurrent_schedule_requests_keep_disk_and_live_interval_in_sync(configured_app):
    app, config = configured_app
    manager = app.extensions["downloads"]
    saved = Event()
    resume = Event()
    second_started = Event()
    set_interval = manager.set_interval

    def pause_before_live_update(minutes):
        if minutes == 60:
            saved.set()
            assert resume.wait(timeout=5)
        set_interval(minutes)

    def request_schedule(minutes):
        with app.test_client() as client:
            if minutes == 15:
                second_started.set()
            return client.post("/downloads/schedule", json={"interval_minutes": minutes}).status_code

    with patch.object(manager, "set_interval", side_effect=pause_before_live_update):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(request_schedule, 60)
            try:
                assert saved.wait(timeout=5)
                second = executor.submit(request_schedule, 15)
                assert second_started.wait(timeout=5)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.1)
            finally:
                resume.set()
            assert first.result(timeout=5) == 200
            assert second.result(timeout=5) == 200

    assert load_yaml(config)["web"]["download_interval_minutes"] == 15
    assert manager.snapshot()["interval_minutes"] == 15


@pytest.mark.parametrize("endpoint", ["/settings", "/trust-sender", "/untrust-sender", "/downloads/schedule"])
def test_partial_config_write_never_replaces_readable_config(configured_app, endpoint):
    app, config = configured_app
    config.write_text("web:\n  trusted_senders: [old@example.com]\n")
    before = config.read_bytes()

    def partial_write(data, dest):
        with open(dest, "w") as stream:
            stream.write("web: [unfinished")
        assert config.read_bytes() == before
        raise OSError("write failed")

    with patch("ownmail.yaml_util.save_yaml", side_effect=partial_write) as save:
        client = app.test_client()
        if endpoint == "/downloads/schedule":
            response = client.post(endpoint, json={"interval_minutes": 60})
            assert response.status_code == 500
        else:
            response = client.post(
                endpoint, data={"email": "old@example.com" if endpoint == "/untrust-sender" else "new@example.com"}
            )
            assert response.status_code in (200, 302)
    save.assert_called_once()
    assert config.read_bytes() == before
    assert not list(config.parent.glob(".ownmail-config-*"))
