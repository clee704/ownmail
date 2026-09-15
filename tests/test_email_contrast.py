"""Synthetic message rendering checks in an actual browser engine."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from flask import render_template
from lxml import html

from tests import test_ui_shell

shell_app = test_ui_shell.shell_app
SANITIZER_DIR = Path(__file__).parents[1] / "ownmail" / "sanitizer"


@pytest.fixture(scope="module")
def contrast_browser():
    node = shutil.which("node")
    required = os.environ.get("OWNMAIL_REQUIRE_BROWSER_TESTS") == "1"
    if not node:
        if required:
            pytest.fail("Node.js is required for message contrast browser tests")
        pytest.skip("Node.js is unavailable")
    probe = subprocess.run(
        [
            node,
            "-e",
            """
const playwright = require(process.env.PLAYWRIGHT_NODE_MODULE || 'playwright');
const engine = playwright[process.env.OWNMAIL_BROWSER_ENGINE || 'chromium'];
engine.launch({headless: true, executablePath: process.env.OWNMAIL_BROWSER_EXECUTABLE})
    .then(browser => browser.close()).catch(error => {console.error(error); process.exitCode = 1;});
""",
        ],
        cwd=SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode:
        if required:
            pytest.fail(probe.stderr)
        pytest.skip("Playwright or its browser is unavailable; install it to run message contrast tests")
    return node


def run_contrast_browser(
    app,
    node,
    body,
    css,
    assertions,
    theme="dark",
    system_theme="light",
    *,
    auto_scale=False,
    viewport=(900, 1400),
    is_mobile=False,
    attachments=(),
    rendered_page=None,
    external_stylesheets=None,
):
    page = rendered_page
    if page is None:
        with app.test_request_context("/email/synthetic"):
            page = render_template(
                "email.html",
                email_id="synthetic",
                subject="Synthetic message",
                sender="sender@example.com",
                body_html=f"<style>{css}</style>{body}",
                supports_dark=True,
                auto_scale=auto_scale,
                attachments=attachments,
            )
    tree = html.fromstring(page)
    paths = tree.xpath('//script[@src]/@src | //link[@rel="stylesheet"]/@href')
    client = app.test_client()
    files = {}
    for path in paths:
        if path.startswith(("https://", "http://", "//")):
            continue
        response = client.get(path)
        assert response.status_code == 200, path
        files[path] = {"body": response.data.decode(), "contentType": response.mimetype}
    payload = {
        "page": page,
        "files": files,
        "theme": theme,
        "systemTheme": system_theme,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "isMobile": is_mobile,
        "externalStylesheets": external_stylesheets or {},
    }
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const playwright = require(process.env.PLAYWRIGHT_NODE_MODULE || 'playwright');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
    const browser = await playwright[process.env.OWNMAIL_BROWSER_ENGINE || 'chromium'].launch({
        headless: true, executablePath: process.env.OWNMAIL_BROWSER_EXECUTABLE
    });
    try {
        const page = await browser.newPage({viewport: input.viewport, colorScheme: input.systemTheme,
            isMobile: input.isMobile, hasTouch: input.isMobile});
        const errors = [];
        const requests = new Map();
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            requests.set(url.href, (requests.get(url.href) || 0) + 1);
            if (url.origin === 'http://ownmail.test' && url.pathname === '/email/synthetic') {
                return route.fulfill({contentType: 'text/html', body: input.page});
            }
            if (url.origin === 'http://ownmail.test' && input.files[url.pathname]) {
                return route.fulfill(input.files[url.pathname]);
            }
            if (Object.hasOwn(input.externalStylesheets, url.href)) {
                return route.fulfill({contentType: 'text/css', body: input.externalStylesheets[url.href]});
            }
            if (url.origin === 'https://fixture.test') {
                return route.fulfill({contentType: 'image/svg+xml',
                    body: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"></svg>'});
            }
            return route.abort();
        });
        await page.addInitScript(theme => {
            localStorage.setItem('ownmail-theme', theme);
            localStorage.setItem('ownmail-sidebar', 'collapsed');
        }, input.theme);
        const settle = async () => {
            await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
            await page.waitForTimeout(100);
        };
        const color = id => page.locator('#' + id).evaluate(element => {
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim()) return getComputedStyle(node.parentElement).color;
            }
            throw new Error('No text found in ' + element.id);
        });
        const background = id => page.locator('#' + id).evaluate(element => getComputedStyle(element).backgroundColor);
        const setTheme = async theme => {
            await page.evaluate(value => {
                localStorage.setItem('ownmail-theme', value);
                applyTheme();
            }, theme);
            await settle();
        };
        await page.goto('http://ownmail.test/email/synthetic', {waitUntil: 'load'});
        await settle();
        __ASSERTIONS__
        assert.deepEqual(errors, []);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", script.replace("__ASSERTIONS__", assertions)],
        input=json.dumps(payload),
        cwd=SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("theme", "system_theme"), [("dark", "light"), ("dark", "dark"), ("auto", "dark")])
def test_repair_missing_and_faint_text_preserves_native_dark_panels(shell_app, contrast_browser, theme, system_theme):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <table role="presentation" style="width:100%;background:white"><tr><td style="background:white;padding:12px">
            <h2 id="missing">Synthetic heading</h2>
        </td></tr></table>
        <div id="callout">Synthetic callout <a id="link" href="https://example.com">Read details</a></div>
        <div id="working">A working dark panel</div>
        """,
        """
        #ownmail-email-content h2 {color:#111111}
        #ownmail-email-content #callout {padding:12px;background:#ffffff;color:#333333}
        #ownmail-email-content #link {color:#006699}
        #ownmail-email-content #working {padding:12px;background:#ffffff;color:#111111}
        @media (prefers-color-scheme:dark) {
            #ownmail-email-content h2 {color:#ffffff !important}
            #ownmail-email-content .absent-panel {background:#222222 !important}
            #ownmail-email-content #callout {color:#eeeeee !important}
            #ownmail-email-content #link {color:#0077aa !important}
            #ownmail-email-content #working {color:#eeeeee;background:#222222}
        }
        """,
        """
        assert.equal(await color('missing'), 'rgb(17, 17, 17)');
        assert.equal(await color('callout'), 'rgb(51, 51, 51)');
        assert.equal(await color('link'), 'rgb(0, 119, 170)');
        assert.equal(await background('callout'), 'rgb(255, 255, 255)');
        assert.equal(await color('working'), 'rgb(238, 238, 238)');
        assert.equal(await background('working'), 'rgb(34, 34, 34)');
        """,
        theme,
        system_theme,
    )


def test_repair_preserves_descendant_colors_and_currentcolor_decoration(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <div id="parent">Missing text <span id="inherited">and inherited text</span>
            <a id="button" href="https://example.com">Keep button</a>
        </div>
        """,
        """
        #ownmail-email-content #parent {padding:12px;background:white;color:#111111;border:2px solid currentColor}
        #ownmail-email-content #button {display:inline-block;padding:4px;background:#111111;
            border:2px solid currentColor;color:white}
        @media (prefers-color-scheme:dark) {
            #ownmail-email-content #parent {color:white !important}
        }
        """,
        """
        assert.equal(await color('parent'), 'rgb(17, 17, 17)');
        assert.equal(await color('inherited'), 'rgb(17, 17, 17)');
        assert.equal(await color('button'), 'rgb(255, 255, 255)');
        assert.equal(await page.locator('#parent').evaluate(el => getComputedStyle(el).borderTopColor),
            'rgb(255, 255, 255)');
        assert.equal(await page.locator('#button').evaluate(el => getComputedStyle(el).borderTopColor),
            'rgb(255, 255, 255)');
        """,
    )


def test_nested_transparent_layout_table_uses_outer_opaque_cell(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <table role="presentation" style="width:100%"><tr><td style="background:white;padding:12px">
            <table role="presentation"><tr><td><p id="text">Text inside nested tables</p></td></tr></table>
        </td></tr></table>
        """,
        """
        #ownmail-email-content #text {color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        "assert.equal(await color('text'), 'rgb(17, 17, 17)');",
    )


def test_existing_low_contrast_and_changed_backgrounds_are_not_recolored(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <p id="preexisting">Already white text</p><p id="moderate">Moderate contrast change</p>
        <p id="background-changed">Different background</p><p id="unchanged">Unchanged foreground</p>
        """,
        """
        #ownmail-email-content p {padding:12px;background:#ffffff;color:#111111}
        #ownmail-email-content #preexisting {color:#ffffff}
        #ownmail-email-content #unchanged {color:#eeeeee}
        @media (prefers-color-scheme:dark) {
            #ownmail-email-content #moderate {color:#999999}
            #ownmail-email-content #background-changed {color:white;background:#eeeeee}
        }
        """,
        """
        assert.equal(await color('preexisting'), 'rgb(255, 255, 255)');
        assert.equal(await color('moderate'), 'rgb(153, 153, 153)');
        assert.equal(await color('background-changed'), 'rgb(255, 255, 255)');
        assert.equal(await color('unchanged'), 'rgb(238, 238, 238)');
        """,
    )


@pytest.mark.parametrize(
    ("attributes", "extra_css"),
    [
        ("", "background-image:linear-gradient(white,white)"),
        ("", "background-image:url(https://fixture.test/background.svg)"),
        ("", "background-color:rgba(255,255,255,.5)"),
        ("", "opacity:.5"),
        ("", "text-shadow:0 0 2px black"),
        ("", "box-shadow:inset 0 0 0 1000px #222222"),
        ("", "filter:brightness(1)"),
        ("", "mix-blend-mode:multiply"),
        ("", "clip-path:inset(1px)"),
        ("", "max-height:0;overflow:hidden"),
        ("hidden", ""),
        ('aria-hidden="true"', ""),
        ('aria-disabled="true"', ""),
    ],
)
def test_ambiguous_or_noncontent_text_is_not_recolored(shell_app, contrast_browser, attributes, extra_css):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        f'<div style="background:white;padding:12px"><div id="excluded" {attributes}>Synthetic text</div></div>',
        f"""
        #ownmail-email-content #excluded {{padding:12px;background:white;color:#111111;{extra_css}}}
        @media (prefers-color-scheme:dark) {{#ownmail-email-content #excluded {{color:white !important}}}}
        """,
        "assert.equal(await color('excluded'), 'rgb(255, 255, 255)');",
    )


def test_table_column_background_is_not_mistaken_for_table_background(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <table style="width:100%;background:white"><colgroup><col style="background:#222"></colgroup>
            <tr><td id="column">Text on a column background</td></tr></table>
        """,
        """
        #ownmail-email-content #column {padding:12px;color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #column {color:white}}
        """,
        "assert.equal(await color('column'), 'rgb(255, 255, 255)');",
    )


def test_overlapping_sibling_background_is_not_treated_as_white_ancestor(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <div style="background:white">
            <div style="position:relative;height:50px;margin-bottom:-50px;background:#222222"></div>
            <p id="text">Text over a sibling background</p>
        </div>
        """,
        """
        #ownmail-email-content #text {margin:0;padding:10px;line-height:30px;color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        "assert.equal(await color('text'), 'rgb(255, 255, 255)');",
    )


def test_theme_swapped_and_moved_text_is_not_recolored(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<p id="swapped">Dark-only text</p><p id="moved">Moved text</p><p id="pseudo">Decorated text</p>',
        """
        #ownmail-email-content p {padding:12px;background:white;color:#111111}
        #ownmail-email-content #swapped {display:none}
        #ownmail-email-content #pseudo::before {content:'*';color:black}
        @media (prefers-color-scheme:dark) {
            #ownmail-email-content p {color:white}
            #ownmail-email-content #swapped {display:block}
            #ownmail-email-content #moved {padding-left:40px}
        }
        """,
        """
        for (const id of ['swapped', 'moved', 'pseudo']) {
            assert.equal(await color(id), 'rgb(255, 255, 255)', id);
        }
        """,
    )


def test_theme_toggles_restore_pristine_inline_declarations(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<p id="text" style="color:rgb(17, 17, 17);padding:12px;background:white">Synthetic text</p>',
        """
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        for (let i = 0; i < 3; i++) {
            assert.equal(await color('text'), 'rgb(17, 17, 17)');
            await setTheme('light');
            assert.deepEqual(await page.locator('#text').evaluate(el => [
                el.style.getPropertyValue('color'), el.style.getPropertyPriority('color')
            ]), ['rgb(17, 17, 17)', '']);
            await setTheme('dark');
        }
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        """,
    )


@pytest.mark.parametrize("system_theme", ["light", "dark"])
def test_light_app_keeps_base_sender_colors(shell_app, contrast_browser, system_theme):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<p id="text">Synthetic text</p><p id="dark-design">An intentionally dark panel</p>',
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        #ownmail-email-content #dark-design {padding:12px;background:#222222;color:white}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        assert.equal(await color('dark-design'), 'rgb(255, 255, 255)');
        assert.equal(await background('dark-design'), 'rgb(34, 34, 34)');
        """,
        "light",
        system_theme,
    )


def test_resizing_reassesses_repairs_without_refetching_resources(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <img src="https://fixture.test/logo.svg" width="40" height="20" alt="Synthetic logo">
        <p id="text">Responsive message text</p>
        """,
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        @media (max-width:600px) {#ownmail-email-content #text {background:#222222}}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        await page.setViewportSize({width:430, height:1400});
        await settle();
        assert.equal(await color('text'), 'rgb(255, 255, 255)');
        assert.equal(await background('text'), 'rgb(34, 34, 34)');
        await page.setViewportSize({width:900, height:1400});
        await settle();
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        await setTheme('light');
        await setTheme('dark');
        assert.equal(requests.get('https://fixture.test/logo.svg'), 1);
        """,
    )


def test_image_load_reassesses_changed_background(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<img id="image" width="40" height="20" alt="Synthetic logo"><p id="text">Synthetic text</p>',
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        await page.evaluate(() => {
            document.getElementById('text').style.backgroundColor = '#222222';
            document.getElementById('image').src = 'https://fixture.test/late.svg';
        });
        await page.waitForFunction(() => document.getElementById('image').complete);
        await settle();
        assert.equal(await color('text'), 'rgb(255, 255, 255)');
        assert.equal(requests.get('https://fixture.test/late.svg'), 1);
        """,
    )


def test_sender_span_selectors_cannot_change_layout_during_repair(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<p id="text">Synthetic text <a id="link" href="https://example.com">Read details</a></p>',
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        #ownmail-email-content #link {color:#006699}
        #ownmail-email-content #text:has(> span) {padding-left:120px !important}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        assert.equal(await color('text'), 'rgb(255, 255, 255)');
        assert.equal(await color('link'), 'rgb(0, 102, 153)');
        assert.equal(await page.locator('#text').evaluate(el => getComputedStyle(el).paddingLeft), '12px');
        """,
    )


def test_sender_span_selectors_cannot_hide_images_during_repair(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        """
        <p id="text">Synthetic text</p>
        <img id="image" src="https://fixture.test/logo.svg" width="40" height="20" alt="Synthetic logo">
        """,
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        #ownmail-email-content #text:has(> span) + img {opacity:0}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        assert.equal(await color('text'), 'rgb(255, 255, 255)');
        assert.equal(await page.locator('#image').evaluate(el => getComputedStyle(el).opacity), '1');
        """,
    )


def test_resource_and_resize_event_bursts_eventually_stop_mutating_content(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<p id="text">Synthetic text</p>',
        """
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content #text {color:white !important}}
        """,
        """
        await page.evaluate(() => {
            window.contentMutations = 0;
            new MutationObserver(records => {window.contentMutations += records.length;}).observe(
                document.getElementById('ownmail-email-content'),
                {subtree:true, childList:true, attributes:true, characterData:true}
            );
            for (let i = 0; i < 25; i++) window.dispatchEvent(new Event('resize'));
        });
        await settle();
        assert.equal(await color('text'), 'rgb(17, 17, 17)');
        const settledMutations = await page.evaluate(() => window.contentMutations);
        await page.waitForTimeout(250);
        assert.equal(await page.evaluate(() => window.contentMutations), settledMutations);
        """,
    )


def test_oversized_messages_keep_native_colors_without_partial_repairs(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<div id="large">' + "<p>Synthetic text</p>" * 5100 + "</div>",
        """
        #ownmail-email-content #large {background:white}
        #ownmail-email-content p {color:#111111}
        @media (prefers-color-scheme:dark) {#ownmail-email-content p {color:white !important}}
        """,
        """
        assert.equal(await color('large'), 'rgb(255, 255, 255)');
        assert.equal(await page.locator('#large').evaluate(el => getComputedStyle(el.lastElementChild).color),
            'rgb(255, 255, 255)');
        assert.equal(await page.locator('#large span').count(), 0);
        """,
    )


def test_baseline_probe_does_not_fetch_assets_unused_by_native_dark_styles(shell_app, contrast_browser):
    app, _ = shell_app
    run_contrast_browser(
        app,
        contrast_browser,
        '<div id="decoration"></div><p id="text">Synthetic text</p>',
        """
        #ownmail-email-content #decoration {width:40px;height:20px;
            background-image:url(https://fixture.test/light-only.svg)}
        #ownmail-email-content #text {padding:12px;background:white;color:#111111}
        @media (prefers-color-scheme:dark) {
            #ownmail-email-content #decoration {background-image:none}
            #ownmail-email-content #text {color:white !important}
        }
        """,
        """
        assert.equal(await color('text'), 'rgb(255, 255, 255)');
        assert.equal(requests.get('https://fixture.test/light-only.svg'), undefined);
        await page.setViewportSize({width:430, height:1400});
        await settle();
        assert.equal(requests.get('https://fixture.test/light-only.svg'), undefined);
        """,
        "dark",
        "dark",
    )
