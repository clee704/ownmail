"""State-changing requests need an exact allowed origin and a valid CSRF token."""

import json
from unittest.mock import MagicMock

import pytest
from lxml import html

from ownmail.web_hosts import resolve_allowed_hosts
from tests.conftest import create_test_app, mock_archive_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SAMPLE_VALUES = {"email_id": "msg1", "index": 0, "name": "a.txt"}
COOKIE = "ownmail_csrf"
EXPIRED = "This page expired, for example because the server restarted. Reload the page and try again."

# Present when this test was written. Discovery must find at least these, so
# a broken discovery cannot pass by finding nothing.
KNOWN_MUTATIONS = {
    ("POST", "/delete-forever"),
    ("POST", "/downloads"),
    ("POST", "/downloads/schedule"),
    ("POST", "/empty-trash"),
    ("POST", "/labels/<email_id>"),
    ("POST", "/restore-bulk"),
    ("POST", "/restore/<email_id>"),
    ("POST", "/settings"),
    ("POST", "/trash-bulk"),
    ("POST", "/trash/<email_id>"),
    ("POST", "/trust-sender"),
    ("POST", "/untrust-sender"),
}
# Flask adds HEAD to every GET rule and answers OPTIONS on every rule.
KNOWN_EXEMPT = {
    ("GET", "/labels/<email_id>"),
    ("HEAD", "/labels/<email_id>"),
    ("OPTIONS", "/labels/<email_id>"),
    ("HEAD", "/downloads"),
    ("OPTIONS", "/empty-trash"),
}


def make_archive(archive_dir):
    archive = MagicMock()
    archive.archive_dir = archive_dir
    archive.auto_expire_trash.return_value = 0
    archive.search.return_value = []
    archive.db = mock_archive_db(get_trashed_emails=[])
    return archive


@pytest.fixture
def archive(tmp_path):
    raw = b"From: Sender <sender@mail.example>\r\nSubject: Synthetic\r\nContent-Type: text/html\r\n\r\n<p>Hello</p>\r\n"
    (tmp_path / "m.eml").write_bytes(raw)
    archive = make_archive(tmp_path)
    archive.db.get_email_by_id.return_value = ("msg1", "m.eml", None, None, None, None)
    archive.db.get_trashed_emails.return_value = [
        ("msg1", "m.eml", "Synthetic", "sender@mail.example", None, "", "2026-01-01", "m.eml", 0)
    ]
    archive.db.get_trash_count.return_value = 1
    return archive


def discover_routes():
    """Every route and method in app.url_map, with a concrete URL."""
    app = create_test_app(make_archive(MagicMock()))
    adapter = app.url_map.bind("localhost")
    found = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda rule: rule.rule):
        for method in sorted(rule.methods):
            values = {name: SAMPLE_VALUES.get(name, "x") for name in rule.arguments}
            url = adapter.build(rule.endpoint, values, method=method)
            found.append(pytest.param(rule.endpoint, method, url, id=f"{method} {rule.rule}"))
    return found


ROUTES = discover_routes()
MUTATIONS = [route for route in ROUTES if route.values[1] not in SAFE_METHODS]
EXEMPT = [route for route in ROUTES if route.values[1] in SAFE_METHODS]


def test_discovery_finds_every_known_route():
    def discovered(routes):
        return {(param.values[1], param.id.split(" ", 1)[1]) for param in routes}

    assert KNOWN_MUTATIONS <= discovered(MUTATIONS)
    assert KNOWN_EXEMPT <= discovered(EXEMPT)


def fresh_token(client, **options):
    response = client.get("/csrf-token", **options)
    assert response.status_code == 200
    return response.json["token"]


def record_view(app, endpoint):
    """Replace one route's handler so a test can tell whether it ran."""
    calls = []
    app.view_functions[endpoint] = lambda **values: calls.append(values) or ("", 204)
    return calls


def record_every_view(app):
    """Replace every handler with a recorder; return the list of endpoints that ran."""
    reached = []

    def recorder(endpoint):
        return lambda **values: reached.append(endpoint) or ("", 204)

    for endpoint in list(app.view_functions):
        app.view_functions[endpoint] = recorder(endpoint)
    return reached


def assert_rejected(response, reason):
    assert response.status_code == 403
    assert response.headers["X-CSRF-Rejected"] == reason
    assert response.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in response.headers


HEADER_CASES = [
    pytest.param({}, False, id="no Origin or Referer"),
    pytest.param({"Origin": "null"}, False, id="null Origin"),
    pytest.param({"Origin": ""}, False, id="empty Origin"),
    pytest.param({"Origin": "http://attacker.invalid"}, False, id="foreign Origin"),
    pytest.param({"Origin": "http://localhost.attacker.invalid"}, False, id="prefix-similar Origin"),
    pytest.param({"Origin": "http://localhost/"}, False, id="Origin with a path"),
    pytest.param({"Origin": "https://localhost"}, False, id="Origin with another scheme"),
    pytest.param({"Origin": "http://localhost:8080"}, False, id="Origin with another port"),
    pytest.param(
        {"Origin": "http://attacker.invalid", "Referer": "http://localhost/search"},
        False,
        id="foreign Origin with matching Referer",
    ),
    pytest.param({"Origin": "null", "Referer": "http://localhost/settings"}, False, id="null Origin with Referer"),
    pytest.param({"Referer": "http://localhost.attacker.invalid/"}, False, id="prefix-similar Referer"),
    pytest.param({"Referer": "http://localhost@attacker.invalid/"}, False, id="Referer with userinfo"),
    pytest.param({"Referer": "http://attacker.invalid/http://localhost/"}, False, id="foreign Referer"),
    pytest.param({"Referer": "http://[::1/"}, False, id="malformed Referer"),
    pytest.param({"Origin": "http://localhost"}, True, id="matching Origin"),
    pytest.param({"Origin": "http://127.0.0.1"}, False, id="Origin of another allowed host"),
    pytest.param({"Referer": "http://localhost/search?q=x"}, True, id="matching Referer without Origin"),
]


@pytest.mark.parametrize("headers,accepted", HEADER_CASES)
@pytest.mark.parametrize("endpoint,method,url", MUTATIONS)
def test_origin_matrix(archive, endpoint, method, url, headers, accepted):
    """With a valid token, only an exactly allowed origin reaches the handler."""
    app = create_test_app(archive)
    calls = record_view(app, endpoint)
    client = app.test_client(csrf=False)
    token = fresh_token(client)
    response = client.open(url, method=method, headers={**headers, "X-CSRF-Token": token})
    if accepted:
        assert response.status_code == 204
        assert len(calls) == 1
    else:
        assert_rejected(response, "origin")
        assert response.json == {"error": "Request rejected: it did not come from an allowed origin."}
        assert calls == []


TOKEN_CASES = ["missing", "empty", "forged", "other cookie", "no cookie", "expired key", "valid"]


def token_for_case(case, archive, app, client):
    """Return the token header value for a case; None leaves it out."""
    token = fresh_token(client)
    if case == "missing":
        return None
    if case == "empty":
        return ""
    if case == "forged":
        return "A" * 43
    if case == "other cookie":
        return fresh_token(app.test_client(csrf=False))
    if case == "no cookie":
        client.delete_cookie(COOKIE)
        return token
    if case == "expired key":
        # A restarted server shares the browser's cookie but not the old key.
        earlier = create_test_app(archive).test_client(csrf=False)
        earlier.set_cookie(COOKIE, client.get_cookie(COOKIE).value)
        return fresh_token(earlier)
    return token


@pytest.mark.parametrize("case", TOKEN_CASES)
@pytest.mark.parametrize("endpoint,method,url", MUTATIONS)
def test_token_matrix(archive, endpoint, method, url, case):
    """From a matching origin, only the token for this browser's cookie and this process passes."""
    app = create_test_app(archive)
    calls = record_view(app, endpoint)
    client = app.test_client(csrf=False)
    token = token_for_case(case, archive, app, client)
    headers = {"Origin": "http://localhost"}
    if token is not None:
        headers["X-CSRF-Token"] = token
    response = client.open(url, method=method, headers=headers)
    if case == "valid":
        assert response.status_code == 204
        assert len(calls) == 1
        return
    assert_rejected(response, "token")
    assert calls == []
    if token is None:
        assert response.mimetype == "text/plain"
        assert response.get_data(as_text=True) == EXPIRED + "\n"
    else:
        assert response.json == {"error": EXPIRED}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "PROPFIND"])
def test_other_methods_are_checked_before_routing(archive, method):
    response = create_test_app(archive).test_client(csrf=False).open("/trash/msg1", method=method)
    assert_rejected(response, "origin")


@pytest.mark.parametrize("endpoint,method,url", EXEMPT)
def test_exempt_methods_never_reach_a_state_changing_view(archive, endpoint, method, url):
    """GET, HEAD and OPTIONS skip both checks, so no view that accepts another method may run for them.

    Flask sends HEAD to the GET view, so a view shared by GET and POST would let
    a forged HEAD with a write payload through.
    """
    app = create_test_app(archive)
    state_changing = {rule.endpoint for rule in app.url_map.iter_rules() if rule.methods - SAFE_METHODS}
    reached = record_every_view(app)
    response = app.test_client(csrf=False).open(
        url,
        method=method,
        headers={"Origin": "http://attacker.invalid"},
        json={"labels": ["Forged"], "ids": ["msg1"]},
    )
    assert not state_changing & set(reached)
    # Flask answers OPTIONS itself; GET and HEAD run the rule's own view once.
    assert reached == ([] if method == "OPTIONS" else [endpoint])
    assert response.status_code in (200, 204)


@pytest.mark.parametrize("method", ["HEAD", "GET"])
def test_label_reads_never_write(archive, method):
    """A non-browser client can send HEAD with a JSON body, a foreign Origin and no token."""
    archive.get_local_labels.return_value = []
    client = create_test_app(archive).test_client(csrf=False)
    response = client.open(
        "/labels/msg1", method=method, headers={"Origin": "http://attacker.invalid"}, json={"labels": ["Forged"]}
    )
    assert response.status_code == 200
    archive.get_local_labels.assert_called_once_with("msg1")
    archive.set_local_labels.assert_not_called()


# Served on port 8080 with nothing configured, so every loopback name is an allowed host.
SERVED_ORIGIN_CASES = [
    pytest.param({"Origin": "http://localhost:8080"}, True, id="own origin"),
    pytest.param({"Referer": "http://localhost:8080/search"}, True, id="own origin in Referer"),
    pytest.param({"Origin": "http://localhost"}, False, id="same name on port 80"),
    pytest.param({"Origin": "http://localhost:80"}, False, id="same name with explicit port 80"),
    pytest.param({"Origin": "http://127.0.0.1"}, False, id="another allowed host on port 80"),
    pytest.param({"Origin": "http://[::1]"}, False, id="IPv6 loopback on port 80"),
    pytest.param({"Origin": "http://127.0.0.1:8080"}, False, id="another allowed host on the serving port"),
    pytest.param({"Origin": "http://[::1]:8080"}, False, id="IPv6 loopback on the serving port"),
    pytest.param({"Origin": "https://localhost:8080"}, False, id="https on the serving port"),
    pytest.param({"Referer": "http://localhost/x"}, False, id="Referer on port 80"),
    pytest.param({"Referer": "http://127.0.0.1:8080/search"}, False, id="Referer from another allowed host"),
]


@pytest.mark.parametrize("headers,accepted", SERVED_ORIGIN_CASES)
def test_only_the_request_origin_is_derived(archive, headers, accepted):
    """Every allowed host and port is a separate origin; a request accepts only the one it was sent to."""
    app = create_test_app(archive, allowed_hosts=resolve_allowed_hosts(None, 8080))
    client = app.test_client(csrf=False)
    token = fresh_token(client, base_url="http://localhost:8080")
    response = client.post("/empty-trash", base_url="http://localhost:8080", headers={**headers, "X-CSRF-Token": token})
    if accepted:
        assert response.status_code == 302
        archive.empty_trash.assert_called_once_with(expired_only=False)
    else:
        assert_rejected(response, "origin")
        archive.empty_trash.assert_not_called()


@pytest.mark.parametrize(
    "scheme,host,origin,accepted",
    [
        ("http", "localhost", "http://localhost", True),
        ("http", "localhost:80", "http://localhost", True),
        ("http", "localhost:80", "http://localhost:80", False),
        ("http", "localhost:443", "http://localhost:443", True),
        ("http", "localhost:443", "http://localhost", False),
        ("https", "localhost:443", "https://localhost", True),
        ("https", "localhost:80", "https://localhost:80", True),
        ("https", "localhost:80", "https://localhost", False),
        ("http", "LOCALHOST:8080", "http://localhost:8080", True),
        ("http", "[0:0::1]:8080", "http://[::1]:8080", True),
    ],
)
def test_request_origin_drops_only_its_own_scheme_default_port(archive, scheme, host, origin, accepted):
    """Browsers omit the scheme's default port from Origin, and only that port."""
    allowed = ["localhost", "localhost:80", "localhost:443", "localhost:8080", "[::1]:8080"]
    client = create_test_app(archive, allowed_hosts=allowed).test_client(csrf=False)
    base_url = f"{scheme}://localhost"
    token = fresh_token(client, base_url=base_url, headers={"Host": host})
    response = client.post(
        "/trash/msg1", base_url=base_url, headers={"Host": host, "Origin": origin, "X-CSRF-Token": token}
    )
    if accepted:
        assert response.status_code == 204
        archive.trash_email.assert_called_once_with("msg1")
    else:
        assert_rejected(response, "origin")
        archive.trash_email.assert_not_called()


# The reported results, at https://mail.example with a mocked archive.
REPORTED_ROWS = [
    pytest.param({}, "origin", id="no headers"),
    pytest.param({"Origin": "null"}, "origin", id="null Origin"),
    pytest.param({"Origin": "https://attacker.invalid"}, "origin", id="foreign Origin"),
    pytest.param({"Referer": "https://mail.example.attacker.invalid/"}, "origin", id="prefix-similar Referer"),
    pytest.param(
        {"Origin": "https://attacker.invalid", "Referer": "https://mail.example/trash"},
        "origin",
        id="foreign Origin with matching Referer",
    ),
    pytest.param({"Origin": "https://mail.example"}, "token", id="matching Origin without a token"),
]


@pytest.mark.parametrize("headers,reason", REPORTED_ROWS)
def test_reported_requests_do_not_delete(archive, headers, reason):
    client = create_test_app(archive, allowed_hosts=["mail.example"]).test_client(csrf=False)
    response = client.post("/delete-forever", base_url="https://mail.example", data={"ids": "msg1"}, headers=headers)
    assert_rejected(response, reason)
    archive.permanently_delete_emails.assert_not_called()


def test_matching_origin_with_token_deletes(archive):
    client = create_test_app(archive, allowed_hosts=["mail.example"]).test_client(csrf=False)
    token = fresh_token(client, base_url="https://mail.example")
    response = client.post(
        "/delete-forever",
        base_url="https://mail.example",
        data={"ids": "msg1"},
        headers={"Origin": "https://mail.example", "X-CSRF-Token": token},
    )
    assert response.status_code == 204
    archive.permanently_delete_emails.assert_called_once_with(["msg1"])


def test_same_origin_message_form_without_token_is_rejected(archive):
    """A form kept in a message body posts from the reader's own origin but cannot know the token."""
    client = create_test_app(archive).test_client(csrf=False)
    client.get("/email/msg1")
    response = client.post("/empty-trash", headers={"Origin": "http://localhost"}, data={"csrf_token": "guess"})
    assert_rejected(response, "token")
    assert response.get_data(as_text=True) == EXPIRED + "\n"
    archive.empty_trash.assert_not_called()


def test_safe_methods_are_not_checked(archive):
    client = create_test_app(archive).test_client(csrf=False)
    assert client.get("/search", headers={"Origin": "http://attacker.invalid"}).status_code == 200
    assert client.head("/search", headers={"Origin": "null"}).status_code == 200
    assert client.options("/trash/msg1").status_code == 200
    archive.trash_email.assert_not_called()


class TestTokenEndpoint:
    def test_returns_uncached_json_without_cors(self, archive):
        client = create_test_app(archive).test_client(csrf=False)
        response = client.get("/csrf-token?callback=leak", headers={"Origin": "http://attacker.invalid"})
        assert response.status_code == 200
        assert response.mimetype == "application/json"
        assert set(response.json) == {"token"}
        assert response.get_data(as_text=True).lstrip().startswith("{")
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert not [name for name in response.headers.keys() if name.lower().startswith("access-control-")]

    def test_preflight_gets_no_cors_grant(self, archive):
        client = create_test_app(archive).test_client(csrf=False)
        response = client.options(
            "/csrf-token",
            headers={"Origin": "http://attacker.invalid", "Access-Control-Request-Method": "GET"},
        )
        assert not [name for name in response.headers.keys() if name.lower().startswith("access-control-")]

    def test_is_get_only(self, archive):
        client = create_test_app(archive).test_client()
        assert client.post("/csrf-token").status_code == 405

    def test_is_host_checked(self, archive):
        response = (
            create_test_app(archive).test_client(csrf=False).get("/csrf-token", headers={"Host": "rebind.invalid"})
        )
        assert response.status_code == 400
        assert "Set-Cookie" not in response.headers

    @pytest.mark.parametrize(
        "base_url,origins,secure",
        [
            ("http://localhost", None, False),
            ("https://localhost", None, True),
            # A TLS-terminating proxy that forwards the browser's Host.
            ("http://mail.example", ["https://mail.example"], True),
            ("http://mail.example:8443", ["https://mail.example:8443"], True),
            # Direct plain-HTTP access to the same server keeps a cookie it can store.
            ("http://192.0.2.10:8080", ["https://mail.example"], False),
            ("http://mail.example", ["http://mail.example"], False),
        ],
    )
    def test_cookie_is_host_only_strict_and_http_only(self, archive, base_url, origins, secure):
        hosts = ["localhost", "mail.example", "mail.example:8443", "192.0.2.10:8080"]
        client = create_test_app(archive, allowed_hosts=hosts, allowed_origins=origins).test_client(csrf=False)
        response = client.get("/csrf-token", base_url=base_url)
        cookie = response.headers["Set-Cookie"]
        attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")[1:]}
        assert cookie.startswith(f"{COOKIE}=")
        assert {"httponly", "samesite", "path"} <= attributes
        assert "SameSite=Strict" in cookie
        assert "domain" not in attributes
        assert "expires" not in attributes and "max-age" not in attributes
        assert ("secure" in attributes) is secure
        assert cookie.split(";")[0] != f"{COOKIE}={response.json['token']}"

    def test_forwarded_proto_does_not_make_the_cookie_secure(self, archive):
        client = create_test_app(archive).test_client(csrf=False)
        response = client.get("/csrf-token", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Ssl": "on"})
        assert "secure" not in response.headers["Set-Cookie"].lower()

    def test_token_is_bound_to_cookie_and_process(self, archive):
        app = create_test_app(archive)
        first, second = app.test_client(csrf=False), app.test_client(csrf=False)
        token = fresh_token(first)
        assert fresh_token(first) == token
        assert "Set-Cookie" not in first.get("/csrf-token").headers
        assert fresh_token(second) != token
        restarted = create_test_app(archive).test_client(csrf=False)
        restarted.set_cookie(COOKIE, first.get_cookie(COOKIE).value)
        assert fresh_token(restarted) != token

    def test_malformed_cookie_is_replaced(self, archive):
        client = create_test_app(archive).test_client(csrf=False)
        client.set_cookie(COOKIE, "short")
        token = fresh_token(client)
        assert client.get_cookie(COOKIE).value != "short"
        response = client.post("/trash/msg1", headers={"Origin": "http://localhost", "X-CSRF-Token": token})
        assert response.status_code == 204


class TestPages:
    @pytest.mark.parametrize("path", ["/search", "/email/msg1", "/settings", "/trash", "/help"])
    def test_pages_carry_the_token_in_a_data_block(self, archive, path):
        client = create_test_app(archive).test_client(csrf=False)
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        token = fresh_token(client)
        page = html.fromstring(response.get_data(as_text=True))
        (block,) = page.xpath('//head/script[@id="ownmail-csrf-token"]')
        assert block.get("type") == "application/json"
        assert json.loads(block.text) == token

    def test_responses_without_a_token_stay_cacheable(self, archive):
        client = create_test_app(archive).test_client(csrf=False)
        response = client.get("/static/style.css")
        assert response.status_code == 200
        assert "no-store" not in response.headers.get("Cache-Control", "")

    def test_reader_keeps_the_token_out_of_forms_and_attributes(self, archive):
        """Message HTML shares the reader page; it must not be able to submit or select the token."""
        client = create_test_app(archive).test_client(csrf=False)
        text = client.get("/email/msg1").get_data(as_text=True)
        token = fresh_token(client)
        assert text.count(token) == 1
        assert not html.fromstring(text).xpath('//input[@name="csrf_token"]')

    @pytest.mark.parametrize("path,action", [("/settings", "/settings"), ("/trash", "/empty-trash")])
    def test_post_forms_carry_the_token_field(self, archive, tmp_path, path, action):
        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        client = create_test_app(archive, config_path=str(config)).test_client(csrf=False)
        page = html.fromstring(client.get(path).get_data(as_text=True))
        (form,) = page.xpath(f'//form[@action="{action}"]')
        assert form.get("method").lower() == "post"
        assert form.xpath('.//input[@name="csrf_token"]/@value') == [fresh_token(client)]


def test_settings_form_from_before_a_restart_asks_for_a_reload(archive, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  page_size: 20\n")
    before = create_test_app(archive, config_path=str(config)).test_client(csrf=False)
    page = html.fromstring(before.get("/settings").get_data(as_text=True))
    stale = page.xpath('//form[@action="/settings"]//input[@name="csrf_token"]/@value')[0]

    after = create_test_app(archive, config_path=str(config)).test_client(csrf=False)
    after.set_cookie(COOKIE, before.get_cookie(COOKIE).value)
    form = {"csrf_token": stale, "page_size": "33"}
    response = after.post("/settings", data=form, headers={"Origin": "http://localhost"})
    assert_rejected(response, "token")
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == EXPIRED + "\n"
    assert "33" not in config.read_text()

    page = html.fromstring(after.get("/settings").get_data(as_text=True))
    form["csrf_token"] = page.xpath('//form[@action="/settings"]//input[@name="csrf_token"]/@value')[0]
    response = after.post("/settings", data=form, headers={"Origin": "http://localhost"})
    assert response.status_code == 302
    assert "page_size: 33" in config.read_text()


class TestAllowedOrigins:
    def test_configured_origins_add_to_the_request_origin(self, archive):
        """Behind a TLS proxy the server sees http, but the browser's origin is https."""
        app = create_test_app(
            archive, allowed_hosts=["mail.example", "localhost"], allowed_origins=["https://mail.example"]
        )
        client = app.test_client(csrf=False)
        token = fresh_token(client, base_url="http://mail.example")

        def post(origin):
            return client.post(
                "/trash/msg1",
                base_url="http://mail.example",
                headers={"Origin": origin, "X-CSRF-Token": token},
            )

        assert post("https://mail.example").status_code == 204
        assert post("http://mail.example").status_code == 204
        assert_rejected(post("http://localhost"), "origin")
        assert_rejected(post("https://mail.example:8443"), "origin")

    def test_forwarded_headers_are_not_trusted(self, archive):
        client = create_test_app(archive, allowed_hosts=["mail.example"]).test_client(csrf=False)
        token = fresh_token(client, base_url="http://mail.example")
        response = client.post(
            "/trash/msg1",
            base_url="http://mail.example",
            headers={
                "Origin": "https://mail.example",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "mail.example",
                "X-CSRF-Token": token,
            },
        )
        assert_rejected(response, "origin")
        archive.trash_email.assert_not_called()

    @pytest.mark.parametrize(
        "entries,expected",
        [
            (None, ()),
            ([], ()),
            (["https://mail.example"], ("https://mail.example",)),
            (["HTTPS://Mail.Example:443/", "https://mail.example"], ("https://mail.example",)),
            (["http://192.0.2.10:80", "http://192.0.2.10:8080"], ("http://192.0.2.10", "http://192.0.2.10:8080")),
            (["https://[2001:DB8::1]:8443"], ("https://[2001:db8::1]:8443",)),
        ],
    )
    def test_entries_are_canonical(self, archive, entries, expected):
        assert create_test_app(archive, allowed_origins=entries).config["allowed_origins"] == expected

    @pytest.mark.parametrize(
        "entries",
        [
            "https://mail.example",
            ["mail.example"],
            ["ftp://mail.example"],
            ["https://"],
            ["https://mail.example/path"],
            ["https://mail.example?query"],
            ["https://mail.example#fragment"],
            ["https://user@mail.example"],
            ["https://mail.example:0"],
            ["https://[::1"],
            ["null"],
            [42],
        ],
    )
    def test_invalid_entries_are_refused(self, archive, entries):
        with pytest.raises(ValueError, match="(?i)allowed origin"):
            create_test_app(archive, allowed_origins=entries)
