"""Download controls against synthetic HTTP responses in a real browser."""

import json
import subprocess
from unittest.mock import patch

from lxml import html

from tests import test_email_contrast, test_ui_shell

shell_app = test_ui_shell.shell_app
download_browser = test_email_contrast.contrast_browser


def run_download_browser(app, node, assertions, *, viewport=(1100, 900)):
    snapshot = {
        "available": True,
        "running": False,
        "state": "idle",
        "interval_minutes": 0,
        "started_at": None,
        "finished_at": None,
        "next_run": None,
    }
    client = app.test_client()
    with patch.object(app.extensions["downloads"], "snapshot", return_value=snapshot):
        response = client.get("/settings")
    assert response.status_code == 200
    page = response.data.decode()
    files = {}
    for path in html.fromstring(page).xpath('//script[@src]/@src | //link[@rel="stylesheet"]/@href'):
        response = client.get(path)
        assert response.status_code == 200, path
        files[path] = {"body": response.data.decode(), "contentType": response.mimetype}
    payload = {
        "page": page,
        "files": files,
        "snapshot": snapshot,
        "viewport": {"width": viewport[0], "height": viewport[1]},
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
        const page = await browser.newPage({viewport: input.viewport, timezoneId: 'UTC'});
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        let state = {...input.snapshot};
        let offline = false;
        let startStatus = 202;
        let scheduleStatus = 200;
        let startGate = null;
        let getCount = 0;
        let settingsLoads = 0;
        const starts = [];
        const schedules = [];
        await page.route('**/*', async route => {
            const request = route.request();
            const url = new URL(request.url());
            if (url.origin !== 'http://ownmail.test') return route.abort();
            if (url.pathname === '/settings') {
                settingsLoads++;
                return route.fulfill({contentType: 'text/html', body: input.page});
            }
            if (input.files[url.pathname]) return route.fulfill(input.files[url.pathname]);
            if (url.pathname === '/downloads' && request.method() === 'GET') {
                getCount++;
                if (offline) return route.abort();
                return route.fulfill({json: state});
            }
            if (url.pathname === '/downloads' && request.method() === 'POST') {
                starts.push(request.postDataJSON());
                if (startGate) await startGate;
                state = {...state, running: startStatus !== 503,
                    state: startStatus === 503 ? 'failed' : 'running', started_at: '2026-01-01T10:00:00Z'};
                return route.fulfill({status: startStatus, json: state});
            }
            if (url.pathname === '/downloads/schedule' && request.method() === 'POST') {
                const body = request.postDataJSON();
                schedules.push(body);
                if (scheduleStatus !== 200) {
                    return route.fulfill({status: scheduleStatus, json: {error: 'Could not save the schedule.'}});
                }
                state = {...state, interval_minutes: body.interval_minutes,
                    next_run: body.interval_minutes ? '2026-01-01T11:00:00Z' : null};
                return route.fulfill({json: state});
            }
            return route.abort();
        });
        await page.goto('http://ownmail.test/settings', {waitUntil: 'load'});
        const start = page.locator('#ownmail-download-now');
        const interval = page.locator('#ownmail-download-interval');
        const save = page.locator('#ownmail-download-save');
        const error = page.locator('#ownmail-download-error');
        const saved = page.locator('#ownmail-download-saved');
        const waitStatus = text => page.waitForFunction(text =>
            document.getElementById('ownmail-download-status').textContent.includes(text), text);
        const refresh = async () => {
            const previous = getCount;
            await page.evaluate(() => window.dispatchEvent(new Event('focus')));
            await page.waitForFunction(() => !document.getElementById('ownmail-download-now').disabled);
            assert.ok(getCount > previous);
        };
        await waitStatus('No download');
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
        cwd=test_email_contrast.SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


def test_manual_download_prevents_duplicates_and_polls_completion_and_failure(shell_app, download_browser):
    app, _ = shell_app
    run_download_browser(
        app,
        download_browser,
        """
        await page.locator('#brand_name').fill('Unsaved appearance');
        let releaseStart;
        startGate = new Promise(resolve => {releaseStart = resolve;});
        await start.evaluate(button => {button.click(); button.click();});
        await page.waitForFunction(() => document.getElementById('ownmail-download-now').disabled);
        await page.waitForTimeout(100);
        assert.deepEqual(starts, [{}]);
        releaseStart();
        await waitStatus('Download in progress');
        assert.ok(await start.isDisabled());
        assert.equal(await page.locator('#ownmail-download-status').getAttribute('aria-live'), 'polite');
        state = {...state, running: false, state: 'succeeded', finished_at: '2026-01-01T10:05:00Z'};
        await waitStatus('Download finished');
        assert.ok(await start.isEnabled());
        assert.equal(await page.locator('#ownmail-download-finished').textContent(),
            await page.evaluate(() => new Date('2026-01-01T10:05:00Z').toLocaleString()));
        startStatus = 503;
        await start.click();
        await waitStatus('Download failed');
        await error.waitFor({state: 'visible'});
        assert.match(await error.textContent(), /server console/);
        assert.ok(await start.isEnabled());
        assert.equal(starts.length, 2);
        assert.equal(await page.locator('#brand_name').inputValue(), 'Unsaved appearance');
        assert.equal(settingsLoads, 1);
        assert.equal(await page.locator('#ownmail-loading-overlay').isVisible(), false);
        """,
    )


def test_schedule_preserves_edits_and_recovers_from_errors_without_reloading(shell_app, download_browser):
    app, _ = shell_app
    run_download_browser(
        app,
        download_browser,
        """
        await page.locator('#brand_name').fill('Keep my draft');
        await interval.selectOption('60');
        offline = true;
        await page.evaluate(() => window.dispatchEvent(new Event('focus')));
        await error.waitFor({state: 'visible'});
        assert.match(await error.textContent(), /Retrying automatically/);
        state = {...state, interval_minutes: 30};
        offline = false;
        await error.waitFor({state: 'hidden'});
        assert.equal(await interval.inputValue(), '60');
        assert.equal(await page.locator('#ownmail-download-current').textContent(),
            'Current schedule: Every 30 minutes.');
        scheduleStatus = 500;
        await save.click();
        await error.waitFor({state: 'visible'});
        assert.equal(await error.textContent(), 'Could not save the schedule.');
        assert.equal(await interval.inputValue(), '60');
        assert.equal(state.interval_minutes, 30);
        assert.equal(await saved.isVisible(), false);
        scheduleStatus = 200;
        await save.click();
        await saved.waitFor({state: 'visible'});
        assert.equal(await error.isVisible(), false);
        assert.equal(state.interval_minutes, 60);
        assert.equal(await interval.inputValue(), '60');
        await refresh();
        assert.equal(await saved.isVisible(), true);
        await interval.selectOption('0');
        await save.click();
        await page.waitForFunction(() => document.getElementById('ownmail-download-current')
            .textContent === 'Current schedule: Off.');
        assert.deepEqual(schedules, [{interval_minutes: 60}, {interval_minutes: 60}, {interval_minutes: 0}]);
        assert.equal(await page.locator('#ownmail-download-next').textContent(), '—');
        assert.equal(await page.locator('#brand_name').inputValue(), 'Keep my draft');
        assert.equal(settingsLoads, 1);
        assert.equal(await page.locator('#ownmail-loading-overlay').isVisible(), false);
        """,
    )


def test_download_controls_fit_phone_viewport(shell_app, download_browser):
    app, _ = shell_app
    run_download_browser(
        app,
        download_browser,
        """
        const bounds = await page.evaluate(() => ({
            viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
            controls: Array.from(document.querySelectorAll('#ownmail-download-form button, #ownmail-download-form select'))
                .map(element => {const rect = element.getBoundingClientRect();
                    return {left: rect.left, right: rect.right, height: rect.height};})
        }));
        assert.ok(bounds.scrollWidth <= bounds.viewport);
        for (const control of bounds.controls) {
            assert.ok(control.left >= 0 && control.right <= bounds.viewport);
            assert.ok(control.height >= 44);
        }
        await interval.selectOption('15');
        await save.click();
        await saved.waitFor({state: 'visible'});
        assert.equal(await interval.inputValue(), '15');
        """,
        viewport=(360, 780),
    )
