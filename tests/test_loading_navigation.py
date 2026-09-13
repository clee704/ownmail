"""Loading feedback during native navigation with synthetic browser responses."""

import json
import subprocess

import pytest
from lxml import html

from tests import test_email_contrast, test_ui_shell

contrast_browser = test_email_contrast.contrast_browser
shell_app = test_ui_shell.shell_app
shell_list_app = test_ui_shell.shell_list_app


def run_loading_browser(app, node, assertions, *, path="/search", theme="light", width=1280):
    client = app.test_client()
    response = client.get(path)
    assert response.status_code == 200
    markup = response.data.decode()
    tree = html.fromstring(markup)
    files = {}
    for asset in tree.xpath('//script[@src]/@src | //link[@rel="stylesheet"]/@href'):
        response = client.get(asset)
        assert response.status_code == 200, asset
        files[asset] = {"body": response.data.decode(), "contentType": response.mimetype}
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
        const page = await browser.newPage({viewport: {width: input.width, height: 900}});
        const errors = [];
        const held = [];
        const waiters = [];
        const snapshots = [];
        const stateWaiters = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => {
            if (!message.text().startsWith('loading-state:')) return;
            const snapshot = JSON.parse(message.text().slice('loading-state:'.length));
            snapshots.push(snapshot);
            for (const waiter of stateWaiters) {
                if (waiter.matches(snapshot)) waiter.resolve(snapshot);
            }
        });
        const current = () => snapshots.at(-1);
        const stateWhere = matches => {
            if (current() && matches(current())) return Promise.resolve(current());
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => reject(new Error('Loading state was not observed: ' + JSON.stringify(current()))), 3000);
                stateWaiters.push({matches, resolve: value => {clearTimeout(timer); resolve(value);}});
            });
        };
        const matching = path => held.filter(item => item.path === path);
        const requestAt = (path, count = 1) => {
            if (matching(path).length >= count) return Promise.resolve(matching(path)[count - 1]);
            return new Promise(resolve => waiters.push({path, count, resolve}));
        };
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://ownmail.test') return route.abort();
            if (url.pathname === input.path) return route.fulfill({contentType: 'text/html', body: input.markup});
            if (input.files[url.pathname]) return route.fulfill(input.files[url.pathname]);
            if (route.request().isNavigationRequest()) {
                const item = {path: url.pathname, route};
                held.push(item);
                for (const waiter of waiters) {
                    if (matching(waiter.path).length >= waiter.count) waiter.resolve(matching(waiter.path)[waiter.count - 1]);
                }
                return;
            }
            return route.abort();
        });
        await page.addInitScript(theme => {
            localStorage.setItem('ownmail-theme', theme);
        }, input.theme);
        await page.goto('http://ownmail.test' + input.path, {waitUntil: 'load'});
        // A pending document navigation stalls frame evaluation; report from the existing document.
        await page.evaluate(() => {
            const rows = Array.from(document.querySelectorAll('.ownmail-email-row'));
            const rect = element => {
                const box = element.getBoundingClientRect();
                return {x: box.x, y: box.y, width: box.width, height: box.height};
            };
            const position = element => {
                const box = rect(element);
                return {x: box.x + box.width / 2, y: box.y + box.height / 2};
            };
            let clicks = 0;
            let keys = 0;
            let keyPrevented = false;
            let last;
            function report() {
                const status = document.getElementById('ownmail-loading-status');
                const snapshot = {
                    clicks, keys, keyPrevented,
                    loading: rows.flatMap((row, index) => row.classList.contains('ownmail-loading') ? [index] : []),
                    checked: rows.map(row => row.querySelector('input[type="checkbox"]').checked),
                    search: document.getElementById('search-input').value,
                    fill: getComputedStyle(document.querySelector('.ownmail-search-form button[type="submit"]')).backgroundColor,
                    status: status && {text: status.textContent, role: status.getAttribute('role'),
                        live: status.getAttribute('aria-live'), hidden: status.hasAttribute('hidden') || status.getAttribute('aria-hidden') === 'true'},
                    targets: {
                        first: position(rows[0].querySelector('.ownmail-email-subject')),
                        second: position(rows[1].querySelector('.ownmail-email-subject')),
                        settings: position(document.querySelector('a[aria-label="Settings"]')),
                        checkbox: position(rows[1].querySelector('input[type="checkbox"]')),
                        search: position(document.getElementById('search-input'))
                    },
                    rows: rows.map(row => {
                        const date = row.querySelector('[id^="date-"]');
                        const spinner = row.querySelector('.ownmail-loading-spinner');
                        const link = row.querySelector('.ownmail-email-row-link');
                        let opacity = 1;
                        for (let element = spinner; element; element = element.parentElement) {
                            opacity *= Number(getComputedStyle(element).opacity);
                        }
                        return {
                            rect: rect(row), dateRect: rect(date), date: date.textContent,
                            dateVisibility: getComputedStyle(date).visibility,
                            disabled: link.getAttribute('aria-disabled'), pointerEvents: getComputedStyle(link).pointerEvents,
                            sender: getComputedStyle(row.querySelector('.ownmail-email-sender')).color,
                            subject: getComputedStyle(row.querySelector('.ownmail-email-subject')).color,
                            spinner: spinner && {rect: {width: spinner.offsetWidth, height: spinner.offsetHeight}, arc: getComputedStyle(spinner).borderTopColor,
                                animation: getComputedStyle(spinner).animationName,
                                decorative: Boolean(spinner.closest('[aria-hidden="true"]')), opacity}
                        };
                    })
                };
                const serialized = JSON.stringify(snapshot);
                if (serialized !== last) console.log('loading-state:' + serialized);
                last = serialized;
            }
            document.addEventListener('click', () => {clicks++; queueMicrotask(report);}, true);
            document.addEventListener('keydown', event => {keys++; keyPrevented = event.defaultPrevented; queueMicrotask(report);});
            document.addEventListener('input', report);
            document.addEventListener('change', report);
            new MutationObserver(report).observe(document.body, {subtree: true, attributes: true, childList: true, characterData: true});
            setInterval(report, 25);
            report();
        });
        const initial = await stateWhere(snapshot => snapshot.rows.length === 2);
        const click = async target => {
            const count = current().clicks;
            const position = current().targets[target];
            await page.mouse.click(position.x, position.y);
            await stateWhere(snapshot => snapshot.clicks > count);
        };
        const release = request => request.route.fulfill({contentType: 'text/html', body: '<h1>' + request.path + '</h1>'});
        const arrive = async request => {
            const navigation = page.waitForURL(url => url.pathname === request.path, {waitUntil: 'load'});
            await release(request);
            await navigation;
            assert.equal(await page.locator('h1').textContent(), request.path);
        };
        __ASSERTIONS__
        assert.deepEqual(errors, []);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", script.replace("__ASSERTIONS__", assertions)],
        input=json.dumps({"markup": markup, "files": files, "path": path, "theme": theme, "width": width}),
        cwd=test_email_contrast.SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("path", ["/search", "/trash"])
def test_repeated_message_click_preserves_visible_feedback(shell_list_app, contrast_browser, path):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        await requestAt('/email/first');
        await stateWhere(snapshot => snapshot.loading.length === 1);
        const checkpoint = snapshots.length;
        await click('first');
        assert.deepEqual(current().loading, [0]);
        assert.equal(current().rows[0].disabled, null);
        assert.equal(current().rows[0].pointerEvents, 'auto');
        assert(snapshots.slice(checkpoint).every(snapshot => snapshot.loading[0] === 0));
        """,
        path=path,
    )


def test_latest_message_navigation_replaces_feedback_and_destination(shell_list_app, contrast_browser):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        const first = await requestAt('/email/first');
        await stateWhere(snapshot => snapshot.loading[0] === 0);
        await click('second');
        const second = await requestAt('/email/second');
        assert.deepEqual(current().loading, []);
        await release(first);
        const loading = await stateWhere(snapshot => snapshot.loading[0] === 1);
        assert.deepEqual(loading.loading, [1]);
        assert.equal(new URL(page.url()).pathname, input.path);
        await arrive(second);
        """,
    )


def test_settings_navigation_clears_pending_message_feedback(shell_list_app, contrast_browser):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        const first = await requestAt('/email/first');
        await stateWhere(snapshot => snapshot.loading[0] === 0);
        await click('settings');
        const settings = await requestAt('/settings');
        assert.deepEqual(current().loading, []);
        await release(first);
        assert.equal(new URL(page.url()).pathname, input.path);
        await arrive(settings);
        """,
    )


def test_fast_message_navigation_does_not_flash_feedback(shell_list_app, contrast_browser):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        const first = await requestAt('/email/first');
        await arrive(first);
        assert(snapshots.every(snapshot => snapshot.loading.length === 0));
        """,
    )


def test_checkbox_and_search_editing_preserve_pending_message(shell_list_app, contrast_browser):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        const first = await requestAt('/email/first');
        await stateWhere(snapshot => snapshot.loading[0] === 0);
        await click('checkbox');
        await stateWhere(snapshot => snapshot.checked[1]);
        await click('search');
        await page.keyboard.type('another query');
        await stateWhere(snapshot => snapshot.search === 'another query');
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.press('Backspace');
        await stateWhere(snapshot => snapshot.search === '');
        assert(current().checked[1]);
        assert.equal(held.length, 1);
        assert.deepEqual(current().loading, [0]);
        await arrive(first);
        """,
    )


def test_escape_cancels_navigation_and_allows_retry(shell_list_app, contrast_browser):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await click('first');
        const first = await requestAt('/email/first');
        await stateWhere(snapshot => snapshot.loading[0] === 0);
        const keys = current().keys;
        await page.keyboard.press('Escape');
        await stateWhere(snapshot => snapshot.keys > keys && snapshot.loading.length === 0);
        assert.equal(current().keyPrevented, false);
        await release(first);
        assert.equal(new URL(page.url()).pathname, input.path);
        await click('first');
        const retry = await requestAt('/email/first', 2);
        await stateWhere(snapshot => snapshot.loading[0] === 0);
        await arrive(retry);
        """,
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_row_spinner_matches_theme_without_shifting_date(shell_list_app, contrast_browser, theme, width):
    run_loading_browser(
        shell_list_app,
        contrast_browser,
        """
        await page.emulateMedia({reducedMotion: 'reduce'});
        await click('first');
        await requestAt('/email/first');
        const loading = await stateWhere(snapshot => snapshot.loading[0] === 0);
        const row = loading.rows[0];
        assert.equal(row.date, initial.rows[0].date);
        assert.deepEqual(row.dateRect, initial.rows[0].dateRect);
        assert.deepEqual(row.rect, initial.rows[0].rect);
        assert.equal(row.dateVisibility, 'hidden');
        assert.equal(row.spinner.arc, 'rgb(237, 185, 40)');
        assert.equal(row.spinner.arc, loading.fill);
        assert.equal(row.spinner.rect.width, 14);
        assert.equal(row.spinner.rect.height, 14);
        assert.equal(row.subject, input.theme === 'light' ? 'rgb(98, 99, 109)' : 'rgb(178, 178, 190)');
        assert.equal(row.sender, row.subject);
        assert.equal(row.spinner.opacity, 1);
        assert(row.spinner.decorative);
        assert.equal(loading.status.role, 'status');
        assert.equal(loading.status.live, 'polite');
        assert(loading.status.text.trim());
        assert.equal(loading.status.hidden, false);
        assert.equal(row.spinner.animation, 'none');
        """,
        theme=theme,
        width=width,
    )
