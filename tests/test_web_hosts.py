"""Host header allowlist: every route answers only configured Host values."""

from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest
from werkzeug.test import EnvironBuilder, run_wsgi_app

from ownmail.web import create_app, run_server
from ownmail.web_hosts import normalize_host, resolve_allowed_hosts
from tests.conftest import create_test_app, mock_archive_db

FOREIGN = "rebind.invalid"
ATTACHMENT = b"synthetic attachment body"


@pytest.fixture
def archive(tmp_path):
    raw = (
        b"From: sender@mail.example\r\nSubject: Host check\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n--b1\r\n'
        b'Content-Type: text/plain\r\nContent-Disposition: attachment; filename="a.txt"\r\n\r\n'
        + ATTACHMENT
        + b"\r\n--b1--\r\n"
    )
    (tmp_path / "m.eml").write_bytes(raw)
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.db = mock_archive_db(get_email_by_id=("msg1", "m.eml", None, None, None, None))
    archive.auto_expire_trash.return_value = 0
    return archive


def serve_defaults(archive):
    """The app as `ownmail serve` builds it on port 8080 with nothing configured."""
    return create_test_app(archive, allowed_hosts=resolve_allowed_hosts(None, 8080))


def get_with_host(app, host):
    """GET /search with a raw Host value, or none; the test client rejects malformed ones itself."""
    environ = EnvironBuilder(path="/search").get_environ()
    del environ["HTTP_HOST"]
    if host is not None:
        environ["HTTP_HOST"] = host
    body, status, _ = run_wsgi_app(app, environ, buffered=True)
    return int(status.split()[0]), b"".join(body)


REQUESTS = [
    ("GET", "/search", {}),
    ("GET", "/static/app-shell.js", {}),
    ("GET", "/favicon.ico", {}),
    ("GET", "/attachment/msg1/0", {}),
    ("GET", "/attachment/msg1/0/a.txt", {}),
    ("GET", "/downloads", {}),
    ("GET", "/no-such-page", {}),
    ("POST", "/empty-trash", {"headers": {"Origin": f"http://{FOREIGN}"}}),
    ("POST", "/downloads/schedule", {"json": {"interval_minutes": 0}, "headers": {"Origin": f"http://{FOREIGN}"}}),
]


@pytest.mark.parametrize("method,path,options", REQUESTS)
@pytest.mark.parametrize("host", [FOREIGN, f"{FOREIGN}:8080"])
def test_foreign_host_gets_400_before_any_route(archive, method, path, options, host):
    """A rebinding name reaches no route, static file, or JSON endpoint, even with a matching Origin."""
    options = {**options, "headers": {**options.get("headers", {}), "Host": host}}
    response = create_test_app(archive).test_client().open(path, method=method, **options)
    assert response.status_code == 400
    assert response.mimetype == "text/plain"
    assert response.get_data() == b"Unrecognized Host header.\n"
    archive.db.get_email_by_id.assert_not_called()
    archive.empty_trash.assert_not_called()


def test_loopback_host_reaches_routes(archive):
    """The same requests addressed to localhost are served, so the 400s come from the Host check."""
    client = create_test_app(archive).test_client()
    assert client.get("/static/app-shell.js").status_code == 200
    attachment = client.get("/attachment/msg1/0")
    assert attachment.status_code == 200
    assert ATTACHMENT in attachment.get_data()
    response = client.post("/empty-trash", headers={"Origin": "http://localhost"})
    assert response.status_code == 302
    archive.empty_trash.assert_called_once_with(expired_only=False)


def test_absent_host_gets_400(archive):
    assert get_with_host(create_test_app(archive), None) == (400, b"Unrecognized Host header.\n")


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost:8080",
        "LocalHost:8080",
        "127.0.0.1",
        "127.0.0.1:8080",
        "[::1]",
        "[::1]:8080",
        "[0:0:0:0:0:0:0:1]:8080",
    ],
)
def test_default_accepts_loopback_with_or_without_serving_port(archive, host):
    assert get_with_host(serve_defaults(archive), host)[0] == 200


@pytest.mark.parametrize(
    "host",
    [
        "localhost:9090",
        "127.0.0.1:80",
        "127.0.0.2",
        "[::2]",
        "[::1]:9090",
        "localhost.rebind.invalid",
        "127.0.0.1.rebind.invalid:8080",
        "192.0.2.10:8080",
        "localhost:",
        "localhost:8080:8080",
        "[::1",
        "user@localhost",
        "",
    ],
)
def test_default_rejects_other_hosts_and_ports(archive, host):
    assert get_with_host(serve_defaults(archive), host) == (400, b"Unrecognized Host header.\n")


@pytest.mark.parametrize(
    "host,status",
    [
        ("mail.example", 200),
        ("MAIL.EXAMPLE:8080", 200),
        ("mail.example:9000", 400),
        ("192.0.2.10:9000", 200),
        ("192.0.2.10", 400),
        ("192.0.2.10:8080", 400),
        ("[2001:DB8::1]:8080", 200),
        ("[2001:db8::1]", 200),
        ("localhost", 400),
        (FOREIGN, 400),
    ],
)
def test_configured_hosts_replace_loopback_defaults(archive, host, status):
    """A port-less entry also accepts the serving port; an entry with a port accepts only that port."""
    allowed = resolve_allowed_hosts(["Mail.Example", "192.0.2.10:9000", "[2001:db8:0::1]"], 8080)
    assert get_with_host(create_test_app(archive, allowed_hosts=allowed), host)[0] == status


def test_resolved_hosts_are_exact_values_in_order():
    assert resolve_allowed_hosts() == ("localhost", "127.0.0.1", "[::1]")
    assert resolve_allowed_hosts(None, 8080) == (
        "localhost",
        "localhost:8080",
        "127.0.0.1",
        "127.0.0.1:8080",
        "[::1]",
        "[::1]:8080",
    )
    assert resolve_allowed_hosts(["mail.example:8080", "Mail.Example"], 8080) == ("mail.example:8080", "mail.example")
    assert resolve_allowed_hosts([], 8080) == resolve_allowed_hosts(None, 8080)


@pytest.mark.parametrize(
    "entries",
    [
        "mail.example",
        {"mail.example": True},
        ["http://mail.example"],
        ["mail.example/"],
        ["mail.example:0"],
        ["mail.example:65536"],
        ["::1"],
        ["[::1"],
        ["[mail.example]"],
        [""],
        [8080],
    ],
)
def test_invalid_entries_are_refused(entries):
    with pytest.raises(ValueError):
        resolve_allowed_hosts(entries, 8080)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_serving_port_is_refused(port):
    with pytest.raises(ValueError, match=f"Invalid port {port}"):
        resolve_allowed_hosts(None, port)


def test_normalize_host_canonicalizes_equivalent_spellings():
    assert normalize_host("Mail.Example:08080") == "mail.example:8080"
    assert normalize_host("[2001:DB8:0:0::1]") == "[2001:db8::1]"
    assert normalize_host("http://mail.example") is None


class TestServeStartup:
    @pytest.fixture
    def sanitizer(self):
        return MagicMock(available=True)

    @pytest.fixture
    def started(self, archive, sanitizer):
        """Run run_server with the sanitizer and the server loop stubbed out."""

        def start(**options):
            with (
                patch("ownmail.sanitizer.HtmlSanitizer", return_value=sanitizer),
                patch("flask.Flask.run") as app_run,
                patch("ownmail.web.create_app", wraps=create_app) as make_app,
            ):
                run_server(archive, **{"open_browser": False, **options})
            return make_app, app_run

        return start

    @pytest.mark.parametrize("port", [0, 65536])
    def test_invalid_port_refuses_before_startup(self, started, sanitizer, capsys, port):
        with pytest.raises(SystemExit) as exc_info:
            started(port=port)
        assert exc_info.value.code == 1
        sanitizer.start.assert_not_called()
        assert f"ERROR: Invalid port {port}." in capsys.readouterr().out

    @pytest.mark.parametrize(
        "host,entries,url",
        [
            ("127.0.0.1", None, "http://127.0.0.1:8080"),
            ("::1", None, "http://[::1]:8080"),
            ("0.0.0.0", None, "http://localhost:8080"),
            ("::", None, "http://localhost:8080"),
            ("0.0.0.0", ["192.0.2.10"], "http://192.0.2.10:8080"),
            ("0.0.0.0", ["mail.example:8443", "192.0.2.10"], "http://192.0.2.10:8080"),
            ("192.0.2.10", ["192.0.2.10"], "http://192.0.2.10:8080"),
            ("192.0.2.10", None, None),
            ("127.0.0.1", ["mail.example"], None),
            ("0.0.0.0", ["mail.example:8443"], None),
        ],
    )
    def test_startup_tab_opens_only_an_allowed_host(self, started, monkeypatch, capsys, host, entries, url):
        """The tab opens an allowed host that reaches the bind address, or serve says why it did not."""
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        with patch("threading.Timer") as timer, patch("webbrowser.open") as browser:
            make_app, _ = started(host=host, port=8080, allowed_hosts=entries, open_browser=True)
            for scheduled in timer.call_args_list:
                scheduled.args[1]()
        out = capsys.readouterr().out
        if url is None:
            browser.assert_not_called()
            assert "Browser not opened: no allowed host reaches this address and port." in out
        else:
            browser.assert_called_once_with(url)
            assert normalize_host(urlsplit(url).netloc) in make_app.call_args.kwargs["allowed_hosts"]
            assert "Browser not opened" not in out

    def test_prints_effective_allowed_hosts(self, started, capsys):
        make_app, _ = started(port=9000)
        assert make_app.call_args.kwargs["allowed_hosts"] == resolve_allowed_hosts(None, 9000)
        out = capsys.readouterr().out
        assert "   Allowed hosts: localhost, localhost:9000, 127.0.0.1, 127.0.0.1:9000, [::1], [::1]:9000\n" in out
        assert "add the address other devices use" not in out

    def test_wildcard_bind_without_configuration_explains_rejections(self, started, capsys):
        started(host="0.0.0.0")
        assert "Only loopback Host names are accepted; add the address other devices use" in capsys.readouterr().out

    def test_configured_hosts_are_used(self, started, capsys):
        make_app, _ = started(host="0.0.0.0", allowed_hosts=["mail.example"])
        assert make_app.call_args.kwargs["allowed_hosts"] == ("mail.example", "mail.example:8080")
        out = capsys.readouterr().out
        assert "   Allowed hosts: mail.example, mail.example:8080\n" in out
        assert "add the address other devices use" not in out

    def test_invalid_configuration_refuses_before_startup(self, started, sanitizer, capsys):
        with pytest.raises(SystemExit) as exc_info:
            started(allowed_hosts=["http://mail.example"])
        assert exc_info.value.code == 1
        sanitizer.start.assert_not_called()
        assert "ERROR: Invalid allowed host 'http://mail.example'" in capsys.readouterr().out
