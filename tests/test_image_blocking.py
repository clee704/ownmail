"""Remote image blocking in the message reader."""

import json
import subprocess
import threading
from contextlib import contextmanager
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest
from lxml import html
from werkzeug.serving import make_server

from ownmail.web import (
    BLOCKED_IMAGE_PLACEHOLDER,
    IMAGE_BLOCKING_CSP,
    _has_remote_images,
    _hide_blocked_images,
    create_app,
)
from tests import test_email_contrast, test_reader_spacing
from tests.conftest import mock_archive_db

contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


@pytest.mark.parametrize(
    "markup",
    [
        '<img src="https://t.test/x.png">',
        '<img src="  HTTP://t.test/x.png">',
        '<img src="//t.test/x.png">',
        '<img src="/\\t.test/x.png">',
        '<img src="/&#9;/t.test/x.png">',
        '<img srcset="images/x.png 1x, https://t.test/x.png 2x">',
        '<img srcset=",https://t.test/x.png">',
        '<picture><source srcset="https://t.test/x.png"></picture>',
        '<table><tr><td background="https://t.test/x.png">Cell</td></tr></table>',
        '<video poster="https://t.test/x.png"></video>',
        '<input type="image" src="https://t.test/x.png">',
        '<div style="background:url(https://t.test/x.png)"></div>',
        '<div style="background:url(&quot;https://t.test/x.png&quot;)"></div>',
        "<body style=\"background-image:url('//t.test/x.png')\"><p>Text</p></body>",
        "<style>.a {background: url( 'https://t.test/x.png' )}</style>",
        '<style>.a {background-image: image-set("https://t.test/x.png" 1x)}</style>',
        "<style>.a {background-image: image-set(url(a.png) 1x, 'https://t.test/x.png' type('image/png') 2x)}</style>",
        "<style>.a {background-image: -webkit-image-set(url(https://t.test/x.png) 1x)}</style>",
        "<style>@font-face {font-family: X; src: url(x.woff2)} li {list-style-image: url(https://t.test/x.png)}</style>",
    ],
)
def test_remote_image_references_are_detected(markup):
    assert _has_remote_images(markup)


@pytest.mark.parametrize(
    "markup",
    [
        '<img src="data:image/png;base64,iVBOR//w0KGgo=">',
        '<img src="images/logo.png" srcset="data:image/png;base64,AA,BB 1x, images/x.png 2x">',
        # The reader drops body attributes other than style.
        '<body background="https://t.test/x.png"><p>Text</p></body>',
        "<style>@font-face {font-family: X; src: url(https://t.test/x.woff2)}</style>",
        '<style>@import url("https://fonts.googleapis.com/css2?family=X");</style>',
        "<style>/* background: url(https://t.test/x.png) */ p {color: red}</style>",
        '<style>a[href^="https://"] {color: blue} p::before {content: "https://t.test/x.png"}</style>',
        '<video><source src="https://t.test/movie.mp4"></video>',
        '<p><a href="https://t.test/">https://t.test/x.png</a></p>',
    ],
)
def test_local_and_non_image_references_are_not_detected(markup):
    assert not _has_remote_images(markup)


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        (
            '<img alt="a > b" width="40" src="https://t.test/x.png?a=1&amp;b=2" srcset="https://t.test/y.png 2x">',
            f'<img alt="a > b" width="40" src="{BLOCKED_IMAGE_PLACEHOLDER}">',
        ),
        (
            '<picture><source srcset="//t.test/dark.png" media="(prefers-color-scheme: dark)">'
            '<img src="data:image/gif;base64,AA"></picture>',
            '<picture><source media="(prefers-color-scheme: dark)"><img src="data:image/gif;base64,AA"></picture>',
        ),
    ],
)
def test_blocked_images_become_placeholders(markup, expected):
    assert _hide_blocked_images(markup) == expected


@pytest.mark.parametrize(
    "markup",
    [
        '<img src="images/x.png" srcset="data:image/png;base64,AA,BB 2x">',
        '<video><source src="https://t.test/movie.mp4"></video>',
        # An attribute value cannot end the tag or start another attribute.
        '<img alt="x src=" width="1"><img alt="&quot;&gt;&lt;img src=&quot;https://t.test/x.png">',
    ],
)
def test_placeholders_leave_other_sources_alone(markup):
    assert _hide_blocked_images(markup) == markup


@pytest.fixture
def message_app(tmp_path):
    def create(markup, **options):
        message = EmailMessage()
        message["Subject"] = "Images"
        message["From"] = "Sender <sender@example.com>"
        message.set_content(markup, subtype="html")
        (tmp_path / "message.eml").write_bytes(message.as_bytes())
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = mock_archive_db()
        archive.db.get_email_by_id.return_value = ("message", "message.eml", None, None, None, None)
        return create_app(archive, **options)

    return create


def open_message(app, query=""):
    response = app.test_client().get("/email/message" + query)
    assert response.status_code == 200
    return response, html.fromstring(response.get_data(as_text=True))


REMOTE_IMAGE = '<p><img src="https://t.test/x.png" width="40"></p>'


def test_blocked_message_sends_csp_and_offers_to_load_images(message_app):
    app = message_app(REMOTE_IMAGE, block_images=True)
    response, page = open_message(app, "?return_to=%2Fsearch%3Fq%3Dsale")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert page.xpath("//*[@id='ownmail-email-content']//img/@src") == [BLOCKED_IMAGE_PLACEHOLDER]
    load = "/email/message?images=load&return_to=/search?q%3Dsale"
    assert page.xpath("//*[@id='load-images-btn']/@data-images-url") == [load]
    assert page.xpath("//*[@id='menu-load-images']/@data-images-url") == [load]
    assert page.xpath("//*[@id='menu-block-images']") == []
    assert page.xpath("//*[@id='ownmail-image-banner']//*[contains(@class, 'ownmail-trust-btn')]")


@pytest.mark.parametrize(
    ("options", "query"),
    [
        ({"block_images": False}, ""),
        ({"block_images": True, "trusted_senders": ["sender@example.com"]}, ""),
        ({"block_images": True}, "?images=load"),
    ],
)
def test_loaded_images_send_no_csp_and_offer_to_block_them(message_app, options, query):
    response, page = open_message(message_app(REMOTE_IMAGE, **options), query)
    assert "Content-Security-Policy" not in response.headers
    assert page.xpath("//*[@id='ownmail-email-content']//img/@src") == ["https://t.test/x.png"]
    assert page.xpath("//*[@id='ownmail-image-banner']") == []
    assert page.xpath("//*[@id='menu-block-images']/@data-images-url") == ["/email/message?images=block"]


@pytest.mark.parametrize("options", [{"block_images": False}, {"trusted_senders": ["sender@example.com"]}])
def test_block_images_overrides_the_default(message_app, options):
    response, page = open_message(message_app(REMOTE_IMAGE, **options), "?images=block")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert page.xpath("//*[@id='ownmail-image-banner']")
    trusted = "trusted_senders" in options
    assert bool(page.xpath("//*[contains(@class, 'ownmail-trust-btn')]")) is not trusted


def test_blocking_does_not_depend_on_detecting_images(message_app):
    app = message_app("<p>No remote images</p>", block_images=True)
    response, page = open_message(app, "?images=other")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert page.xpath("//*[@id='ownmail-image-banner'] | //*[@data-images-url]") == []


def test_block_images_setting_applies_to_the_next_message(message_app):
    app = message_app(REMOTE_IMAGE, block_images=True)
    assert "Content-Security-Policy" in open_message(app)[0].headers
    app.config["block_images"] = False
    assert "Content-Security-Policy" not in open_message(app)[0].headers


# Every image source the sanitizer keeps, each fetched from its own path
REMOTE_IMAGE_MESSAGE = """<html><head><style>
.sheet {height:20px;background-image:url("https://fixture.test/style-block.svg")}
.set {height:20px;background-image:image-set("https://fixture.test/image-set.svg" 1x)}
</style></head>
<body style="background-image:url(&quot;https://fixture.test/body.svg&quot;)">
<img id="plain" width="40" height="20" alt="Plain" src="https://fixture.test/img.svg">
<img id="responsive" width="40" height="20" alt="Responsive" src="https://fixture.test/fallback.svg"
    srcset="https://fixture.test/srcset.svg 1x, https://fixture.test/srcset-2x.svg 2x">
<picture><source srcset="https://fixture.test/picture.svg">
    <img id="picture" width="40" height="20" alt="Picture" src="https://fixture.test/picture-fallback.svg"></picture>
<img id="scheme-relative" width="40" height="20" alt="Scheme-relative" src="//fixture.test/scheme-relative.svg">
<table background="https://fixture.test/table.svg"><tr>
    <td background="https://fixture.test/cell.svg">Cell</td></tr></table>
<div style="height:20px;background:url(https://fixture.test/inline.svg)"></div>
<ul style="list-style-image:url('https://fixture.test/list.svg')"><li>Item</li></ul>
<div class="sheet"></div><div class="set"></div>
<video width="40" height="20" poster="https://fixture.test/poster.svg"></video>
<input type="image" width="40" height="20" alt="Submit" src="https://fixture.test/input.svg">
</body></html>"""

LOADED_PATHS = [
    "/body.svg",
    "/cell.svg",
    "/image-set.svg",
    "/img.svg",
    "/inline.svg",
    "/input.svg",
    "/list.svg",
    "/picture.svg",
    "/poster.svg",
    "/scheme-relative.svg",
    "/srcset.svg",
    "/style-block.svg",
    "/table.svg",
]

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
        const page = await browser.newPage({viewport: {width: 900, height: 1400}});
        const errors = [];
        let remote = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.origin === input.base) return route.continue();
            if (url.hostname === 'fixture.test') {
                remote.push(url.pathname);
                return route.fulfill({contentType: 'image/svg+xml',
                    body: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"></svg>'});
            }
            return route.abort();
        });
        const settle = async () => {
            await page.waitForLoadState('load');
            await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
            await page.waitForTimeout(200);
        };
        const requested = () => [...new Set(remote)].sort();
        const assertRequested = (expected) => assert.deepEqual(requested(), expected, 'Requested ' + requested().join(', '));
        const navigate = async action => {
            remote = [];
            await Promise.all([page.waitForNavigation(), action()]);
            await settle();
        };
        const imageWidths = () => page.locator('#ownmail-email-content img').evaluateAll(
            images => images.map(image => image.naturalWidth));
        await page.goto(input.base + input.path);
        await settle();
        __ASSERTIONS__
        assert.deepEqual(errors, []);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.fixture
def image_app(tmp_path, spacing_sanitizer):
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message.set_content(REMOTE_IMAGE_MESSAGE, subtype="html")
    (tmp_path / "synthetic.eml").write_bytes(message.as_bytes())
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.auto_expire_trash.return_value = 0
    archive.search.return_value = []
    archive.db = mock_archive_db()
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    return create_app(archive, block_images=True, sanitizer=spacing_sanitizer)


@contextmanager
def serve(app):
    """Serve the app on a local port so the browser follows its reloads."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def run_image_browser(app, node, path, assertions):
    with serve(app) as base:
        result = subprocess.run(
            [node, "-e", BROWSER_SCRIPT.replace("__ASSERTIONS__", assertions)],
            input=json.dumps({"base": base, "path": path}),
            cwd=test_email_contrast.SANITIZER_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
    assert result.returncode == 0, result.stderr


def test_blocked_images_stay_unrequested_until_loaded(image_app, contrast_browser):
    run_image_browser(
        image_app,
        contrast_browser,
        "/email/synthetic?return_to=%2Fsearch%3Fq%3Dsale",
        """
        const loaded = __LOADED__;
        assertRequested([]);
        assert(await page.locator('#ownmail-image-banner').isVisible());
        // Blocked images keep their authored size instead of collapsing to alt text.
        assert.deepEqual(await imageWidths(), [1, 1, 1, 1]);

        await navigate(() => page.locator('#load-images-btn').click());
        const url = new URL(page.url());
        assert.equal(url.searchParams.get('images'), 'load');
        assert.equal(url.searchParams.get('return_to'), '/search?q=sale');
        assertRequested(loaded);
        assert.equal(await page.locator('#ownmail-image-banner').count(), 0);
        assert.deepEqual(await imageWidths(), [40, 40, 40, 40]);
        assert.equal(await page.locator('#ownmail-back-to-results').getAttribute('href'), '/search?q=sale');

        await page.locator('.ownmail-email-menu summary').click();
        await navigate(() => page.locator('#menu-block-images').click());
        assert.equal(new URL(page.url()).searchParams.get('images'), 'block');
        assertRequested([]);
        assert(await page.locator('#ownmail-image-banner').isVisible());
        assert.deepEqual(await imageWidths(), [1, 1, 1, 1]);
        """.replace("__LOADED__", json.dumps(LOADED_PATHS)),
    )


def test_trusting_sender_reloads_the_message_with_images(image_app, contrast_browser):
    run_image_browser(
        image_app,
        contrast_browser,
        "/email/synthetic?return_to=%2Fsearch%3Fq%3Dsale",
        """
        assertRequested([]);
        await navigate(() => page.locator('.ownmail-trust-btn').click());
        const url = new URL(page.url());
        assert.equal(url.searchParams.get('images'), null);
        assert.equal(url.searchParams.get('return_to'), '/search?q=sale');
        assertRequested(__LOADED__);
        assert.equal(await page.locator('#ownmail-image-banner').count(), 0);
        assert.equal(await page.locator('#ownmail-action-message').textContent(), 'Sender trusted.');
        """.replace("__LOADED__", json.dumps(LOADED_PATHS)),
    )
