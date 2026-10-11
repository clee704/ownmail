"""Pytest fixtures for ownmail tests."""

import os
import select
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers


class CsrfTestClient(FlaskClient):
    """Send state-changing requests as the app's own pages do.

    Each one gets a token from GET /csrf-token and, unless the test sets Origin
    or Referer, a same-origin Origin. ``app.test_client(csrf=False)`` sends
    requests exactly as written.
    """

    def __init__(self, *args, csrf=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.csrf = csrf
        self.tokens = {}

    def open(self, *args, **kwargs):
        method = kwargs.get("method", "GET").upper()
        if self.csrf and method not in ("GET", "HEAD", "OPTIONS") and args and isinstance(args[0], str):
            headers = Headers(kwargs.get("headers"))
            base = urlsplit(kwargs.get("base_url") or "http://localhost")
            host = headers.get("Host", base.netloc)
            if "Origin" not in headers and "Referer" not in headers:
                headers["Origin"] = f"{base.scheme}://{host}"
            if "X-CSRF-Token" not in headers:
                if (base, host) not in self.tokens:
                    response = self.get("/csrf-token", base_url=kwargs.get("base_url"), headers={"Host": host})
                    self.tokens[base, host] = response.json["token"] if response.status_code == 200 else ""
                headers["X-CSRF-Token"] = self.tokens[base, host]
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


@pytest.fixture(autouse=True)
def csrf_test_client(monkeypatch):
    """Make app.test_client() pass the CSRF checks for tests of other behavior."""
    monkeypatch.setattr(Flask, "test_client_class", CsrfTestClient)


# Launching a browser costs up to a second and a half, so each test process
# starts one Playwright browser server. Test scripts connect to it and create
# their own context, which keeps cookies, storage and routes per test. Port 0
# and the per-process endpoint let pytest-xdist workers each run their own.
BROWSER_SERVER = """
const playwright = require(process.env.PLAYWRIGHT_NODE_MODULE || 'playwright');
(async () => {
    const server = await playwright[process.env.OWNMAIL_BROWSER_ENGINE || 'chromium'].launchServer({
        headless: true, executablePath: process.env.OWNMAIL_BROWSER_EXECUTABLE, host: '127.0.0.1', port: 0
    });
    server.on('close', () => { console.error('The browser closed unexpectedly'); process.exit(1); });
    // pytest closes stdin at session end, or by exiting if it dies first.
    process.stdin.on('end', async () => {
        server.removeAllListeners('close');
        await server.close();
        process.exit(0);
    });
    process.stdin.resume();
    console.log(server.wsEndpoint());
})().catch(error => { console.error(error); process.exit(1); });
"""


@pytest.fixture(scope="session")
def browser_server():
    """Start the shared browser server, or skip unless OWNMAIL_REQUIRE_BROWSER_TESTS=1."""
    required = os.environ.get("OWNMAIL_REQUIRE_BROWSER_TESTS") == "1"
    node = shutil.which("node")
    if not node:
        if required:
            pytest.fail("Node.js is required for browser tests")
        pytest.skip("Node.js is unavailable")
    with tempfile.TemporaryFile("w+") as log:
        server = subprocess.Popen(
            [node, "-e", BROWSER_SERVER],
            cwd=Path(__file__).parents[1] / "ownmail" / "sanitizer",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
        )
        try:
            ready, _, _ = select.select([server.stdout], [], [], 30)
            endpoint = server.stdout.readline().strip() if ready else ""
            if not endpoint:
                server.kill()
                server.wait()
                log.seek(0)
                if required:
                    pytest.fail(f"Could not start the browser:\n{log.read()}")
                pytest.skip("Playwright or its browser is unavailable; install it to run browser tests")
            with pytest.MonkeyPatch.context() as env:
                env.setenv("OWNMAIL_BROWSER_WS_ENDPOINT", endpoint)
                yield node, server, log
        finally:
            if server.poll() is None:
                server.stdin.close()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


@pytest.fixture
def browser_node(browser_server):
    """Path to Node; scripts connect to OWNMAIL_BROWSER_WS_ENDPOINT instead of launching."""
    node, server, log = browser_server
    if server.poll() is not None:
        log.seek(0)
        pytest.fail(f"The shared browser server exited with status {server.returncode}:\n{log.read()}")
    return node


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def mock_archive_db(**overrides):
    """A stand-in ArchiveDatabase for tests that only exercise the web layer.

    web.py's context processor asks for the stats and the label sidebar on every
    template render, and those need real ints and dicts — a bare MagicMock
    returns mocks that blow up on comparison and iteration. Pass keyword
    overrides for whatever a given test actually cares about:

        db = mock_archive_db(get_email_count=100)
    """
    db = MagicMock()
    db.get_email_count.return_value = 0
    db.get_trash_count.return_value = 0
    db.get_label_counts.return_value = {}
    db.get_role_counts.return_value = {}
    db.get_system_labels.return_value = set()
    db.gmail_accounts = frozenset()
    for name, value in overrides.items():
        getattr(db, name).return_value = value
    return db


class PassthroughSanitizer:
    """Returns message HTML unchanged, for web tests that do not exercise sanitization.

    Production code has no passthrough: create_app refuses to run without an
    available sanitizer, so only tests can construct an app with this one.
    """

    available = True

    def sanitize(self, html: str):
        return html, True, False

    def stop(self):
        pass


def create_test_app(archive, **options):
    """create_app with a PassthroughSanitizer, unless the test passes its own sanitizer."""
    from ownmail.web import create_app

    options.setdefault("sanitizer", PassthroughSanitizer())
    return create_app(archive, **options)


@pytest.fixture
def sample_eml_simple():
    """A simple plain text email."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 1 Jan 2024 10:00:00 +0000
Message-ID: <test123@example.com>

This is a test email body.
"""


@pytest.fixture
def sample_eml_html():
    """An HTML email."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Test
Date: Tue, 2 Jan 2024 12:00:00 +0000
Message-ID: <html456@example.com>
Content-Type: text/html; charset="utf-8"

<html>
<body>
<h1>Hello World</h1>
<p>This is an HTML email.</p>
</body>
</html>
"""


@pytest.fixture
def sample_eml_multipart():
    """A multipart email with attachment."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Email with Attachment
Date: Wed, 3 Jan 2024 14:00:00 +0000
Message-ID: <multi789@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset="utf-8"

This email has an attachment.

--boundary123
Content-Type: application/pdf; name="document.pdf"
Content-Disposition: attachment; filename="document.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRv
Ymo=

--boundary123--
"""


@pytest.fixture
def sample_eml_korean():
    """An email with Korean characters (common encoding issues)."""
    return """From: =?UTF-8?B?7ZWc6rWt7Ja0?= <korean@example.com>
To: recipient@example.com
Subject: =?UTF-8?B?7ZWc6riAIO2FjOyKpO2KuA==?=
Date: Thu, 4 Jan 2024 16:00:00 +0900
Message-ID: <korean@example.com>
Content-Type: text/plain; charset="utf-8"

안녕하세요, 테스트 이메일입니다.
""".encode()


@pytest.fixture
def sample_eml_malformed():
    """A malformed email with embedded CR/LF in headers."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Test with
 continuation line
Date: Fri, 5 Jan 2024 18:00:00 +0000
Message-ID: <malformed@example.com>

Body text.
"""


@pytest.fixture
def sample_eml_with_labels():
    """An email with labels (stored in DB, not in .eml headers)."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Labeled Email
Date: Sat, 6 Jan 2024 20:00:00 +0000
Message-ID: <labeled@example.com>

This email has labels.
"""
