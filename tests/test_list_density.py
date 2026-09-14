"""Browser regressions for the desktop display density preference."""

import json
import subprocess

import pytest
from lxml import html

from tests import test_email_contrast, test_ui_shell

shell_app = test_ui_shell.shell_app
shell_list_app = test_ui_shell.shell_list_app
contrast_browser = test_email_contrast.contrast_browser


def run_density_browser(app, node, assertions, preference=None):
    client = app.test_client()
    files = {}
    for path in ["/settings", "/search?q=annual", "/trash", "/downloads"]:
        response = client.get(path)
        assert response.status_code == 200, path
        files[path] = {"body": response.data.decode(), "contentType": response.mimetype}
        if response.mimetype == "text/html":
            tree = html.fromstring(response.data)
            for asset in tree.xpath('//script[@src]/@src | //link[@rel="stylesheet"]/@href'):
                asset_response = client.get(asset)
                assert asset_response.status_code == 200, asset
                files[asset] = {"body": asset_response.data.decode(), "contentType": asset_response.mimetype}
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
        const context = await browser.newContext({viewport: {width: 1280, height: 900}});
        const errors = [];
        context.on('page', tab => tab.on('pageerror', error => errors.push(error.message)));
        await context.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://ownmail.test') return route.abort();
            if (url.pathname === '/blank') return route.fulfill({contentType: 'text/html', body: ''});
            const resource = input.files[url.pathname + url.search];
            return resource ? route.fulfill(resource) : route.abort();
        });
        const page = await context.newPage();
        await page.goto('http://ownmail.test/blank');
        await page.evaluate(preference => {
            localStorage.setItem('ownmail-sidebar', 'collapsed');
            if (preference !== null) localStorage.setItem('ownmail-list-density', preference);
        }, input.preference);
        const visit = path => page.goto('http://ownmail.test' + path, {waitUntil: 'load'});
        const density = () => page.locator('html').getAttribute('data-list-density');
        const rowHeight = () => page.locator('.ownmail-email-row').first().evaluate(
            row => row.getBoundingClientRect().height);
        const sidebarHeights = () => page.locator('#ownmail-sidebar .ownmail-sidebar-scroll a').evaluateAll(
            links => Object.fromEntries(links.map(link => [link.getAttribute('aria-label'),
                link.getBoundingClientRect().height])));
        __ASSERTIONS__
        assert.deepEqual(errors, []);
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        [node, "-e", script.replace("__ASSERTIONS__", assertions)],
        input=json.dumps({"files": files, "preference": preference}),
        cwd=test_email_contrast.SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("preference", [None, "invalid-density"])
def test_missing_or_invalid_preference_defaults_to_standard(shell_list_app, contrast_browser, preference):
    run_density_browser(
        shell_list_app,
        contrast_browser,
        """
        await visit('/settings');
        assert.equal(await density(), 'standard');
        assert.equal(await page.getByLabel('Display density', {exact: true}).inputValue(), 'standard');
        """,
        preference,
    )


def test_density_setting_persists_and_changes_message_and_sidebar_spacing(shell_list_app, contrast_browser):
    run_density_browser(
        shell_list_app,
        contrast_browser,
        """
        const heights = {};
        const navigationHeights = {};
        for (const preference of ['comfortable', 'standard', 'compact']) {
            await visit('/settings');
            const selector = page.getByLabel('Display density', {exact: true});
            await selector.selectOption(preference);
            assert.equal(await density(), preference);
            assert.equal(await page.evaluate(() => localStorage.getItem('ownmail-list-density')), preference);
            navigationHeights[preference] = await sidebarHeights();
            await page.locator('#ownmail-sidebar-toggle').click();
            assert(await page.locator('.ownmail-sidebar-labels .ownmail-sidebar-label').first().isVisible());
            assert.deepEqual(await sidebarHeights(), navigationHeights[preference]);
            await page.locator('#ownmail-sidebar-toggle').click();
            await page.reload();
            assert.equal(await selector.inputValue(), preference);
            assert.deepEqual(await sidebarHeights(), navigationHeights[preference]);
            await visit('/search?q=annual');
            assert.equal(await density(), preference);
            heights[preference] = await rowHeight();
            for (const path of ['/search?q=annual', '/trash']) {
                await visit(path);
                assert.equal(await density(), preference);
                assert.equal(await rowHeight(), heights[preference]);
                assert.deepEqual(await sidebarHeights(), navigationHeights[preference]);
                const checkbox = page.locator('.ownmail-email-checkbox input').first();
                await checkbox.check();
                assert(await checkbox.isChecked());
                assert.equal(await page.locator('#ownmail-selection-count').textContent(), '1 selected');
                assert.equal(await rowHeight(), heights[preference]);
            }
        }
        assert(heights.comfortable > heights.standard, JSON.stringify(heights));
        assert(heights.standard > heights.compact, JSON.stringify(heights));
        assert(navigationHeights.standard['All Mail'] > 0);
        assert(navigationHeights.standard.Work > 0);
        for (const name of Object.keys(navigationHeights.standard)) {
            const sizes = ['comfortable', 'standard', 'compact'].map(preference => navigationHeights[preference][name]);
            assert(sizes[0] > sizes[1] && sizes[1] > sizes[2], name + ': ' + sizes.join(', '));
        }
        """,
    )


@pytest.mark.parametrize("width", [430, 900])
def test_density_keeps_mobile_row_and_drawer_spacing(shell_list_app, contrast_browser, width):
    run_density_browser(
        shell_list_app,
        contrast_browser,
        """
        await page.setViewportSize({width: WIDTH, height: 900});
        await visit('/search?q=annual');
        const spacing = () => page.locator('.ownmail-email-row').first().evaluate(row => ({
            height: row.getBoundingClientRect().height,
            linkPadding: getComputedStyle(row.querySelector('.ownmail-email-row-link')).padding,
            senderPadding: getComputedStyle(row.querySelector('.ownmail-email-sender')).padding
        }));
        const baseline = await spacing();
        await page.locator('#ownmail-sidebar-toggle').click();
        const drawerBaseline = await sidebarHeights();
        assert(drawerBaseline['All Mail'] > 0);
        assert(drawerBaseline.Work > 0);
        for (const preference of ['comfortable', 'compact']) {
            await page.evaluate(value => localStorage.setItem('ownmail-list-density', value), preference);
            await page.reload();
            assert.equal(await density(), preference);
            assert.deepEqual(await spacing(), baseline);
            await page.locator('#ownmail-sidebar-toggle').click();
            assert.deepEqual(await sidebarHeights(), drawerBaseline);
        }
        """.replace("WIDTH", str(width)),
    )


def test_cached_list_restores_density_on_pageshow(shell_list_app, contrast_browser):
    run_density_browser(
        shell_list_app,
        contrast_browser,
        """
        await visit('/search?q=annual');
        const standardHeight = await rowHeight();
        await page.evaluate(() => {
            localStorage.setItem('ownmail-list-density', 'compact');
            window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        });
        assert.equal(await density(), 'compact');
        assert(await rowHeight() < standardHeight);
        """,
    )


def test_open_lists_and_settings_follow_preferences_from_another_tab(shell_list_app, contrast_browser):
    run_density_browser(
        shell_list_app,
        contrast_browser,
        """
        await visit('/search?q=annual');
        const standardHeight = await rowHeight();

        const settings = await context.newPage();
        await settings.goto('http://ownmail.test/settings');
        const selector = settings.getByLabel('Display density', {exact: true});
        assert.equal(await selector.inputValue(), 'standard');
        await selector.selectOption('compact');
        await page.waitForFunction(() => document.documentElement.dataset.listDensity === 'compact');
        const compactHeight = await rowHeight();
        assert(compactHeight < standardHeight);
        await selector.selectOption('comfortable');
        await page.waitForFunction(() => document.documentElement.dataset.listDensity === 'comfortable');
        assert(await rowHeight() > standardHeight);

        await page.evaluate(() => localStorage.setItem('ownmail-list-density', 'standard'));
        await settings.waitForFunction(() => document.getElementById('ownmail-list-density').value === 'standard');
        await settings.close();
        """,
    )
