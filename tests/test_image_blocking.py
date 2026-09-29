"""Remote content blocking in the message reader."""

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
    _has_remote_content,
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
        "<style>@font-face {font-family: X; src: local(X), url(//t.test/x.woff2)}</style>",
        '<style>@import url("https://fonts.googleapis.com/css2?family=X");</style>',
        "<style>@import 'https://fonts.googleapis.com/css2?family=X';</style>",
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X">',
        '<video src="https://t.test/movie.mp4"></video>',
        '<video><source src="https://t.test/movie.mp4"></video>',
        '<audio src="//t.test/sound.mp3"></audio>',
        '<video><track src="https://t.test/captions.vtt"></video>',
    ],
)
def test_remote_references_are_detected(markup):
    assert _has_remote_content(markup)


@pytest.mark.parametrize(
    "markup",
    [
        '<img src="data:image/png;base64,iVBOR//w0KGgo=">',
        '<img src="images/logo.png" srcset="data:image/png;base64,AA,BB 1x, images/x.png 2x">',
        # The reader drops body attributes other than style.
        '<body background="https://t.test/x.png"><p>Text</p></body>',
        "<style>@font-face {font-family: X; src: local(X), url(fonts/x.woff2)}</style>",
        "<style>/* @import url(https://t.test/x.css); background: url(https://t.test/x.png) */ p {color: red}</style>",
        '<style>a[href^="https://"] {color: blue} p::before {content: "https://t.test/x.png"}</style>',
        '<p><a href="https://t.test/">https://t.test/x.png</a></p>',
    ],
)
def test_local_and_inert_references_are_not_detected(markup):
    assert not _has_remote_content(markup)


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
REMOTE_FONT = '<style>@font-face {font-family:X;src:url(https://t.test/x.woff2)}</style><p style="font-family:X">X</p>'


@pytest.mark.parametrize(("markup", "images"), [(REMOTE_IMAGE, [BLOCKED_IMAGE_PLACEHOLDER]), (REMOTE_FONT, [])])
def test_blocked_message_sends_csp_and_offers_to_load_content(message_app, markup, images):
    app = message_app(markup, block_images=True)
    response, page = open_message(app, "?return_to=%2Fsearch%3Fq%3Dsale")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert page.xpath("//*[@id='ownmail-email-content']//img/@src") == images
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


# Every remote source the sanitizer keeps, each fetched from its own path. The
# sanitizer keeps stylesheets only from trusted font providers.
REMOTE_CONTENT_MESSAGE = """<html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/link.css">
<style>
@import url("https://fonts.googleapis.com/import.css");
@font-face {font-family:Remote;src:url(https://fixture.test/font.woff2)}
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
<p style="font-family:Remote">Remote font</p><p style="font-family:Link">Linked font</p>
<p style="font-family:Import">Imported font</p>
<video width="40" height="20" src="https://fixture.test/video.mp4"></video>
<video width="40" height="20"><source src="https://fixture.test/source.mp4"></video>
<audio src="https://fixture.test/audio.mp3"></audio>
</body></html>"""

LOADED_PATHS = [
    "/audio.mp3",
    "/body.svg",
    "/cell.svg",
    "/font.woff2",
    "/image-set.svg",
    "/img.svg",
    "/import.css",
    "/import.woff2",
    "/inline.svg",
    "/input.svg",
    "/link.css",
    "/link.woff2",
    "/list.svg",
    "/picture.svg",
    "/poster.svg",
    "/scheme-relative.svg",
    "/source.mp4",
    "/srcset.svg",
    "/style-block.svg",
    "/table.svg",
    "/video.mp4",
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
            remote.push(url.pathname);
            if (url.pathname.endsWith('.svg')) {
                return route.fulfill({contentType: 'image/svg+xml',
                    body: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"></svg>'});
            }
            if (url.pathname.endsWith('.css')) {
                // A font provider's stylesheet names a font file on the provider's host.
                const name = url.pathname.slice(1, -'.css'.length);
                return route.fulfill({contentType: 'text/css',
                    body: `@font-face {font-family: ${name}; src: url(https://fonts.gstatic.com/${name}.woff2)}`});
            }
            return route.fulfill({body: ''});
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
def browser_message_app(tmp_path, spacing_sanitizer):
    def build(markup):
        message = EmailMessage()
        message["Subject"] = "Synthetic message"
        message["From"] = "Sender <sender@example.com>"
        message.set_content(markup, subtype="html")
        (tmp_path / "synthetic.eml").write_bytes(message.as_bytes())
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.auto_expire_trash.return_value = 0
        archive.search.return_value = []
        archive.db = mock_archive_db()
        archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
        return create_app(archive, block_images=True, sanitizer=spacing_sanitizer)

    return build


@pytest.mark.parametrize("wrapper", ["p", "body", "html", "head"])
def test_attribute_markup_handler_stays_inert_when_blocked_and_loaded(browser_message_app, contrast_browser, wrapper):
    # A <link> the sender wrote inside an attribute value carries event handlers.
    # If body extraction lifts it out as a live element, the CSP allows inline
    # handlers, so onerror fires while blocked and onload fires once loaded.
    handler = "window.__ownmail_pwned=true"
    link = f"<link rel=stylesheet href=https://t.test/pwn.css onload={handler} onerror={handler}>"
    prefix = {"p": "", "body": ">", "html": "<body>", "head": "<body>"}[wrapper]
    markup = '<html><head></head><body><p id="host">Hi</p></body></html>'
    start = '<p id="host">' if wrapper == "p" else f"<{wrapper}>"
    markup = markup.replace(start, start[:-1] + f' title="{prefix}{link}">')
    run_image_browser(
        browser_message_app(markup),
        contrast_browser,
        "/email/synthetic",
        """
        const assertInert = async () => {
            assert.equal(await page.evaluate(() => window.__ownmail_pwned === true), false);
            assert.equal(await page.locator('#ownmail-email-content link').count(), 0);
            assert.equal(await page.locator('#host').textContent(), 'Hi');
            const title = await page.locator('#host').getAttribute('title');
            assert.equal(Boolean(title && title.includes('pwn.css')), __RETAINED__);
            assertRequested([]);
        };
        // Blocked (default): the CSP is active and allows inline handlers.
        await assertInert();

        await page.goto(input.base + '/email/synthetic?images=load');
        await settle();
        // Loaded: no CSP; a lifted <link> would fetch and fire onload instead.
        await assertInert();
        """.replace("__RETAINED__", json.dumps(wrapper == "p")),
    )


@pytest.fixture
def image_app(tmp_path, spacing_sanitizer):
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message.set_content(REMOTE_CONTENT_MESSAGE, subtype="html")
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
