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
from ownmail.web_hosts import resolve_allowed_hosts
from tests import test_email_contrast, test_reader_spacing
from tests.conftest import create_test_app, mock_archive_db

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
        (
            '<img alt="<img src=" src="https://t.test/x.png">',
            f'<img alt="<img src=" src="{BLOCKED_IMAGE_PLACEHOLDER}">',
        ),
        (
            '<img alt="<img srcset=" srcset="https://t.test/x.png 2x" src="https://t.test/fallback.png">',
            f'<img alt="<img srcset=" src="{BLOCKED_IMAGE_PLACEHOLDER}">',
        ),
        (
            '<source title="<source srcset=" srcset="https://t.test/x.png">',
            '<source title="<source srcset=">',
        ),
        (
            '<p title="<source">before<img src="https://t.test/x.png">after"</p>',
            f'<p title="<source">before<img src="{BLOCKED_IMAGE_PLACEHOLDER}">after"</p>',
        ),
        (
            '<p title="<img">before<video src="https://t.test/movie.mp4"></video>after"</p>'
            '<img src="https://t.test/x.png">',
            '<p title="<img">before<video src="https://t.test/movie.mp4"></video>after"</p>'
            f'<img src="{BLOCKED_IMAGE_PLACEHOLDER}">',
        ),
        (
            '<!doctype html>\n<!-- <img src="https://t.test/inert.png"> -->\n'
            '<p title="a > b">A &amp; B</p>\r\n<IMG\n alt="<img src="\n src="https://t.test/x.png" />',
            '<!doctype html>\n<!-- <img src="https://t.test/inert.png"> -->\n'
            f'<p title="a > b">A &amp; B</p>\r\n<IMG\n alt="<img src="\n src="{BLOCKED_IMAGE_PLACEHOLDER}" />',
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
        return create_test_app(archive, **options)

    return create


def open_message(app, query=""):
    response = app.test_client().get("/email/message" + query)
    assert response.status_code == 200
    return response, html.fromstring(response.get_data(as_text=True))


@pytest.mark.parametrize(
    "markup",
    [
        '<img alt="<img src=" src="https://fixture.test/real.svg">',
        '<img alt="<img srcset=" srcset="https://fixture.test/real.svg 1x" src="https://fixture.test/fallback.svg">',
        '<picture><source title="<source srcset=" srcset="https://fixture.test/picture.svg">'
        '<img src="https://fixture.test/fallback.svg"></picture>',
        '<p title="<source">before<img src="https://fixture.test/real.svg">after"</p>',
        '<p title="<img">before<video src="https://fixture.test/movie.mp4"></video>after"</p>',
    ],
)
def test_sanitized_attribute_markup_preserves_dom_and_real_image_rewrites(message_app, spacing_sanitizer, markup):
    # A complete image-looking attribute is a control, not itself a failing rewrite.
    markup = '<p title="<img src=a.png>">Control</p>' + markup + REMOTE_IMAGE
    app = message_app(markup, block_images=True, sanitizer=spacing_sanitizer)
    _, loaded = open_message(app, "?images=load")
    _, blocked = open_message(app)
    original = list(loaded.get_element_by_id("ownmail-email-content").iterdescendants())
    rewritten = list(blocked.get_element_by_id("ownmail-email-content").iterdescendants())
    assert len(rewritten) == len(original)
    for before, after in zip(original, rewritten):
        assert (after.tag, after.text, after.tail) == (before.tag, before.text, before.tail)
        expected = dict(before.attrib)
        if before.tag in {"img", "source"}:
            expected.pop("srcset", None)
        if before.tag == "img":
            expected["src"] = BLOCKED_IMAGE_PLACEHOLDER
        assert dict(after.attrib) == expected
    assert original[0].get("title") == "<img src=a.png>"


REMOTE_IMAGE = '<p><img src="https://t.test/x.png" width="40"></p>'
REMOTE_FONT = '<style>@font-face {font-family:X;src:url(https://t.test/x.woff2)}</style><p style="font-family:X">X</p>'


@pytest.mark.parametrize(("markup", "images"), [(REMOTE_IMAGE, [BLOCKED_IMAGE_PLACEHOLDER]), (REMOTE_FONT, [])])
def test_blocked_message_sends_csp_and_offers_to_load_content(message_app, markup, images):
    app = message_app(markup, block_images=True)
    response, page = open_message(app, "?return_to=%2Fsearch%3Fq%3Dsale")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert "'unsafe-inline'" not in IMAGE_BLOCKING_CSP.split("script-src ")[1].split(";")[0]
    assert page.xpath("//*[@id='ownmail-email-content']//img/@src") == images
    load = "/email/message?images=load&return_to=/search?q%3Dsale"
    assert page.xpath("//*[@id='load-images-btn']/@data-images-url") == [load]
    assert page.xpath("//*[@id='menu-load-images']/@data-images-url") == [load]
    actions = page.get_element_by_id("ownmail-reader-actions")
    assert actions.get("data-sender") == "sender@example.com"
    assert actions.get("data-email-id") == "message"
    assert actions.get("data-reload-url") == "/email/message?return_to=/search?q%3Dsale"
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
def test_loaded_images_restrict_scripts_and_offer_to_block_them(message_app, options, query):
    response, page = open_message(message_app(REMOTE_IMAGE, **options), query)
    assert response.headers["Content-Security-Policy"] == "script-src 'self'"
    assert page.xpath("//*[@id='ownmail-email-content']//img/@src") == ["https://t.test/x.png"]
    assert page.xpath("//*[@id='ownmail-image-banner']") == []
    assert page.xpath("//*[@id='menu-block-images']/@data-images-url") == ["/email/message?images=block"]


@pytest.mark.parametrize("options", [{"block_images": False}, {"trusted_senders": ["sender@example.com"]}])
def test_block_images_overrides_the_default(message_app, options):
    response, page = open_message(message_app(REMOTE_IMAGE, **options), "?images=block")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert "'unsafe-inline'" not in IMAGE_BLOCKING_CSP.split("script-src ")[1].split(";")[0]
    assert page.xpath("//*[@id='ownmail-image-banner']")
    trusted = "trusted_senders" in options
    assert bool(page.xpath("//*[contains(@class, 'ownmail-trust-btn')]")) is not trusted


def test_blocking_does_not_depend_on_detecting_images(message_app):
    app = message_app("<p>No remote images</p>", block_images=True)
    response, page = open_message(app, "?images=other")
    assert response.headers["Content-Security-Policy"] == IMAGE_BLOCKING_CSP
    assert "'unsafe-inline'" not in IMAGE_BLOCKING_CSP.split("script-src ")[1].split(";")[0]
    assert page.xpath("//*[@id='ownmail-image-banner'] | //*[@data-images-url]") == []


def test_block_images_setting_applies_to_the_next_message(message_app):
    app = message_app(REMOTE_IMAGE, block_images=True)
    assert "Content-Security-Policy" in open_message(app)[0].headers
    app.config["block_images"] = False
    assert open_message(app)[0].headers["Content-Security-Policy"] == "script-src 'self'"


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
        const response = await page.goto(input.base + input.path);
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
    # Ensure extraction keeps the attribute inert independently of CSP.
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
        // Blocked (default): no live link should exist.
        await assertInert();

        await page.goto(input.base + '/email/synthetic?images=load');
        await settle();
        // Loaded: a lifted link would make a remote request.
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
    # As ownmail serve does, accept loopback names with the serving port.
    app.config["allowed_hosts"] = resolve_allowed_hosts(None, server.server_port)
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


@pytest.mark.parametrize("source", [False, True])
def test_attribute_markup_cannot_hide_real_image_sources(message_app, spacing_sanitizer, contrast_browser, source):
    markup = '<p id="host" title="<img src=a.png>">Control</p>'
    if source:
        markup += '<picture><source id="source" title="<source srcset=" srcset="https://fixture.test/picture.svg">'
        markup += '<img id="real" src="https://fixture.test/fallback.svg"></picture>'
    else:
        markup += '<img id="real" alt="<img src=" src="https://fixture.test/real.svg">'
    app = message_app(markup, block_images=True, sanitizer=spacing_sanitizer)
    run_image_browser(
        app,
        contrast_browser,
        "/email/message",
        """
        assertRequested([]);
        assert.equal(await page.locator('#host').getAttribute('title'), '<img src=a.png>');
        assert.equal(await page.locator('#host').textContent(), 'Control');
        assert.equal(await page.locator('#ownmail-email-content img').count(), 1);
        assert.equal(await page.locator('#real').getAttribute('src'), __PLACEHOLDER__);
        if (__SOURCE__) {
            assert.equal(await page.locator('#source').getAttribute('title'), '<source srcset=');
            assert.equal(await page.locator('#source').getAttribute('srcset'), null);
        } else {
            assert.equal(await page.locator('#real').getAttribute('alt'), '<img src=');
        }
        """.replace("__PLACEHOLDER__", json.dumps(BLOCKED_IMAGE_PLACEHOLDER)).replace("__SOURCE__", json.dumps(source)),
    )


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


@pytest.mark.parametrize("query", ["", "?images=load"])
def test_reader_app_markup_uses_only_external_scripts(message_app, query):
    _, page = open_message(message_app(REMOTE_IMAGE, block_images=True), query)
    assert not page.xpath("//script[not(@src)]")
    assert all(script.get("src").startswith("/static/") for script in page.xpath("//script"))
    assert not [(node.tag, attr) for node in page.iter() for attr in node.attrib if attr.lower().startswith("on")]


@pytest.mark.parametrize("query", ["", "?images=load"])
def test_csp_blocks_retained_handler_while_reader_controls_work(message_app, contrast_browser, query):
    # Deliberately retain a benign handler to test the response policy independently
    # of sanitizer correctness. The browser must receive the actual Flask headers.
    handler = "window.__retainedHandlerRan = true"
    markup = (
        f'<button id="retained-handler" onclick="{handler}">Synthetic handler</button>'
        '<button id="spoofed-control" data-reader-action="trash" data-show-loading '
        'data-images-url="/email/message?images=load">Untrusted control</button>' + REMOTE_IMAGE
    )
    sanitizer = MagicMock()
    sanitizer.sanitize.side_effect = lambda body: (body, True, False)
    app = message_app(markup, block_images=True, sanitizer=sanitizer)
    run_image_browser(
        app,
        contrast_browser,
        "/email/message" + query,
        """
        const policy = response.headers()['content-security-policy'];
        assert.equal(policy.split('script-src ')[1].split(';')[0], "'self'");
        const retained = page.locator('#retained-handler');
        assert.equal(await retained.getAttribute('onclick'), 'window.__retainedHandlerRan = true');
        await page.evaluate(() => {
            window.__retainedClicks = 0;
            document.getElementById('retained-handler').addEventListener('click', () => window.__retainedClicks++);
        });
        await retained.click();
        assert.equal(await page.evaluate(() => window.__retainedClicks), 1);
        assert.equal(await page.evaluate(() => window.__retainedHandlerRan), undefined);
        const dialogs = [];
        page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
        const start = page.url();
        await page.locator('#spoofed-control').click();
        await page.waitForTimeout(250);
        assert.equal(page.url(), start);
        assert.deepEqual(dialogs, []);
        assert.equal(await page.locator('#ownmail-loading-overlay').getAttribute('class'), 'ownmail-loading-overlay');
        await page.locator('#ownmail-message-details-toggle').click();
        assert.equal(await page.locator('#ownmail-message-details-toggle').getAttribute('aria-expanded'), 'true');
        assert(await page.locator('#ownmail-message-metadata').isVisible());
        // The reader hides its app header on mobile; exercise the shell on desktop.
        await page.setViewportSize({width: 1200, height: 1400});
        await page.locator('#ownmail-sidebar-toggle').click();
        assert.equal(await page.locator('#ownmail-sidebar-toggle').getAttribute('aria-expanded'), 'false');
        await page.locator('#ownmail-sidebar-toggle').click();
        assert.equal(await page.locator('#ownmail-sidebar-toggle').getAttribute('aria-expanded'), 'true');
        await page.locator('.ownmail-email-menu summary').click();
        await navigate(() => page.locator('[id^="menu-"][data-images-url]').click());
        assert.notEqual(page.url(), start);
        assert.equal(await page.evaluate(() => window.__retainedHandlerRan), undefined);
        """,
    )
