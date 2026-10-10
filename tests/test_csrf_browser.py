"""Reader and settings actions work in a real browser with CSRF checks, across a server restart."""

import json
import subprocess
import threading
from contextlib import contextmanager
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest
from werkzeug.serving import make_server

from ownmail.web import create_app
from ownmail.web_hosts import resolve_allowed_hosts
from ownmail.yaml_util import load_yaml
from tests import test_email_contrast, test_reader_spacing
from tests.conftest import mock_archive_db

contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer

# A sender's form aimed at a mutation route. The sanitizer unwraps forms, so
# the tests that submit it render the message without the real sanitizer.
MESSAGE = (
    "<p>Synthetic newsletter</p>"
    '<img src="https://fixture.test/pixel.png" alt="">'
    '<form action="/empty-trash" method="post"><input type="hidden" name="csrf_token" value="guess">'
    '<button id="retained-submit">Claim prize</button></form>'
)
EXPIRED = "This page expired, for example because the server restarted. Reload the page and try again."

BROWSER_SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const playwright = require(process.env.PLAYWRIGHT_NODE_MODULE || 'playwright');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
    const browser = await playwright[process.env.OWNMAIL_BROWSER_ENGINE || 'chromium'].launch({
        headless: true, executablePath: process.env.OWNMAIL_BROWSER_EXECUTABLE
    });
    try {
        const context = await browser.newContext();
        await context.route('**/*', route =>
            new URL(route.request().url()).origin === input.base ? route.continue() : route.abort());
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('dialog', dialog => dialog.accept());
        // State-changing requests and token refreshes, with the rejection reason if any.
        const log = [];
        context.on('response', async response => {
            const request = response.request();
            const path = new URL(request.url()).pathname;
            if (request.method() === 'GET' && path !== '/csrf-token') return;
            const entry = [request.method(), path, response.status()];
            const reason = await response.headerValue('X-CSRF-Rejected');
            log.push(reason ? [...entry, reason] : entry);
        });
        const requests = async () => {
            await page.waitForTimeout(100);
            return log.splice(0);
        };
        // Swap in a freshly created app, as a restarted server would be.
        const restart = async () => assert.equal((await fetch(input.base + '/__restart')).status, 204);
        const openMenu = () => page.locator('.ownmail-email-menu summary').click();
        const navigate = async action => {
            await Promise.all([page.waitForNavigation(), action()]);
            await page.waitForLoadState('load');
        };
        const settled = () => page.waitForFunction(() =>
            document.getElementById('ownmail-action-feedback').dataset.state === 'success');
        __ASSERTIONS__
        assert.deepEqual(errors, []);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.fixture
def archive(tmp_path):
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@mail.example>"
    message.set_content(MESSAGE, subtype="html")
    (tmp_path / "msg1.eml").write_bytes(message.as_bytes())
    state = {"trashed_at": None}

    def set_trashed(value):
        def update(email_id):
            state["trashed_at"] = value
            return True

        return update

    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.auto_expire_trash.return_value = 0
    archive.search.return_value = []
    archive.db = mock_archive_db(get_labels_for_email=[], get_trash_count=1)
    archive.db.get_email_by_id.side_effect = lambda email_id: (
        "msg1",
        "msg1.eml",
        None,
        None,
        None,
        state["trashed_at"],
    )
    archive.db.get_trashed_emails.return_value = [
        ("msg1", "msg1.eml", "Synthetic message", "sender@mail.example", None, "", "2026-01-01", "msg1.eml", 0)
    ]
    archive.trash_email.side_effect = set_trashed("2026-01-01T00:00:00")
    archive.restore_email.side_effect = set_trashed(None)
    archive.get_local_labels.return_value = ["Synthetic"]
    archive.set_local_labels.return_value = True
    return archive


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("web:\n  page_size: 20\n")
    return path


@contextmanager
def serve(build):
    """Serve build(allowed_hosts); GET /__restart replaces the app with a new one."""
    current = {}

    def dispatch(environ, start_response):
        if environ["PATH_INFO"] == "/__restart":
            current["app"] = build(current["hosts"])
            start_response("204 No Content", [])
            return [b""]
        return current["app"](environ, start_response)

    server = make_server("127.0.0.1", 0, dispatch, threaded=True)
    current["hosts"] = resolve_allowed_hosts(None, server.server_port)
    current["app"] = build(current["hosts"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def run_browser(node, archive, config, sanitizer, assertions):
    def build(hosts):
        return create_app(archive, config_path=str(config), sanitizer=sanitizer, allowed_hosts=hosts)

    with serve(build) as base:
        result = subprocess.run(
            [node, "-e", BROWSER_SCRIPT.replace("__ASSERTIONS__", assertions)],
            input=json.dumps({"base": base, "expired": EXPIRED}),
            cwd=test_email_contrast.SANITIZER_DIR,
            capture_output=True,
            text=True,
            timeout=90,
        )
    assert result.returncode == 0, result.stderr


def test_reader_actions_work_and_recover_after_restart(contrast_browser, spacing_sanitizer, archive, config):
    run_browser(
        contrast_browser,
        archive,
        config,
        spacing_sanitizer,
        """
        await page.goto(input.base + '/email/msg1?return_to=%2Fsearch');
        await openMenu();
        await navigate(() => page.locator('#menu-trust-sender').click());
        assert.deepEqual(await requests(), [['POST', '/trust-sender', 200]]);

        await openMenu();
        await page.locator('#menu-untrust-sender').click();
        await settled();
        assert.deepEqual(await requests(), [['POST', '/untrust-sender', 200]]);

        await openMenu();
        await page.locator('#ownmail-edit-labels').click();
        await page.locator('#ownmail-label-input:enabled').fill('Kept');
        await page.locator('#ownmail-label-add').click();
        await navigate(() => page.locator('#ownmail-label-save').click());
        assert.deepEqual(await requests(), [['POST', '/labels/msg1', 200]]);

        // The open page's token predates the restart: one refresh, then success.
        await restart();
        await openMenu();
        await navigate(() => page.locator('#ownmail-reader-actions [data-reader-action="trash"]').click());
        assert.equal(new URL(page.url()).pathname, '/search');
        assert.deepEqual(await requests(), [
            ['POST', '/trash/msg1', 403, 'token'], ['GET', '/csrf-token', 200], ['POST', '/trash/msg1', 204]
        ]);

        await page.goto(input.base + '/email/msg1');
        await openMenu();
        await navigate(() => page.locator('#ownmail-reader-actions [data-reader-action="restore"]').click());
        await openMenu();
        await navigate(() => page.locator('#ownmail-reader-actions [data-reader-action="trash"]').click());
        await page.goto(input.base + '/email/msg1');
        await openMenu();
        await navigate(() => page.locator('#ownmail-reader-actions [data-reader-action="delete-forever"]').click());
        assert.equal(new URL(page.url()).pathname, '/trash');
        assert.deepEqual(await requests(), [
            ['POST', '/restore/msg1', 204], ['POST', '/trash/msg1', 204], ['POST', '/delete-forever', 204]
        ]);
        """,
    )
    assert archive.trash_email.call_count == 2
    archive.restore_email.assert_called_once_with("msg1")
    archive.permanently_delete_emails.assert_called_once_with(["msg1"])
    archive.set_local_labels.assert_called_once_with("msg1", ["Synthetic", "Kept"])
    assert load_yaml(config)["web"]["trusted_senders"] == []


def test_noreferrer_message_form_cannot_post_a_mutation(contrast_browser, archive, config):
    """A message form with rel=noreferrer posts with Origin: null and is rejected before the route runs."""
    sanitizer = MagicMock()
    sanitizer.sanitize.side_effect = lambda body: (
        body.replace("<form ", '<form target="_blank" rel="noopener noreferrer" '),
        True,
        False,
    )
    run_browser(
        contrast_browser,
        archive,
        config,
        sanitizer,
        """
        await page.goto(input.base + '/email/msg1');
        assert.equal(await page.locator('#ownmail-email-content form[action="/empty-trash"][rel~="noreferrer"]').count(), 1,
            'The form renders, so the request checks must stop it');
        const [popup] = await Promise.all([context.waitForEvent('page'), page.locator('#retained-submit').click()]);
        await popup.waitForLoadState();
        const logged = await requests();
        assert.equal(logged.length, 1);
        const [method, path, status, reason] = logged[0];
        assert.deepEqual([method, path, status], ['POST', '/empty-trash', 403]);
        assert(['origin', 'token'].includes(reason));
        """,
    )
    archive.empty_trash.assert_not_called()


def test_same_origin_message_form_is_stopped_by_the_token(contrast_browser, archive, config):
    """Without noreferrer the browser sends the reader's own Origin, and only the token stops the form."""
    sanitizer = MagicMock()
    sanitizer.sanitize.side_effect = lambda body: (body, True, False)
    run_browser(
        contrast_browser,
        archive,
        config,
        sanitizer,
        """
        await page.goto(input.base + '/email/msg1');
        await navigate(() => page.locator('#retained-submit').click());
        assert.equal((await page.locator('body').innerText()).trim(), input.expired);
        assert.deepEqual(await requests(), [['POST', '/empty-trash', 403, 'token']]);
        """,
    )
    archive.empty_trash.assert_not_called()


def test_plain_forms_and_json_controls_work_and_expire_after_restart(
    contrast_browser, spacing_sanitizer, archive, config
):
    run_browser(
        contrast_browser,
        archive,
        config,
        spacing_sanitizer,
        """
        const submitSettings = () => page.locator('form[action="/settings"] button[type="submit"]').click();
        await page.goto(input.base + '/settings');
        await page.locator('#page_size').fill('33');
        await restart();
        await navigate(submitSettings);
        assert.equal((await page.locator('body').innerText()).trim(), input.expired);
        assert.deepEqual(await requests(), [['POST', '/settings', 403, 'token']]);

        await page.goto(input.base + '/settings');
        await page.locator('#page_size').fill('33');
        await navigate(submitSettings);
        assert.equal(new URL(page.url()).search, '?saved=1');
        assert.deepEqual(await requests(), [['POST', '/settings', 302]]);

        await page.locator('#ownmail-download-interval:enabled').selectOption('15');
        await page.locator('#ownmail-download-save').click();
        await page.locator('#ownmail-download-saved:visible').waitFor();
        assert.deepEqual(await requests(), [['POST', '/downloads/schedule', 200]]);

        await page.goto(input.base + '/trash');
        await navigate(() => page.locator('.ownmail-empty-trash-btn').click());
        assert.deepEqual(await requests(), [['POST', '/empty-trash', 302]]);
        """,
    )
    web = load_yaml(config)["web"]
    assert web["page_size"] == 33
    assert web["download_interval_minutes"] == 15
    archive.empty_trash.assert_called_once_with(expired_only=False)
