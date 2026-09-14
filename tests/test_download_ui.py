"""Download controls against synthetic HTTP responses in a real browser."""

import json
import subprocess
from unittest.mock import patch

import pytest
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
        "has_progress": False,
        "phase": None,
        "source": None,
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "failure_reason": None,
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
                if (offline) return route.abort();
                return route.fulfill({json: state});
            }
            if (url.pathname === '/downloads' && request.method() === 'POST') {
                starts.push(request.postDataJSON());
                if (startGate) await startGate;
                state = {...state, running: startStatus !== 503,
                    state: startStatus === 503 ? 'failed' : 'running', started_at: '2026-01-01T10:00:00Z',
                    phase: 'starting', source: null, has_progress: false, downloaded: 0, skipped: 0, errors: 0,
                    failure_reason: startStatus === 503 ? 'Download process could not be started.' : null};
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
        const progress = page.locator('#ownmail-download-progress');
        const counts = page.locator('#ownmail-download-counts');
        const waitStatus = text => page.waitForFunction(text =>
            document.getElementById('ownmail-download-status').textContent.includes(text), text);
        const refresh = async () => {
            const response = page.waitForResponse(response => new URL(response.url()).pathname === '/downloads' &&
                response.request().method() === 'GET');
            await page.evaluate(() => window.dispatchEvent(new Event('focus')));
            await response;
        };
        await waitStatus('Ready to download');
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
        await waitStatus('Starting download');
        assert.ok(await start.isDisabled());
        assert.equal(await progress.isVisible(), false);
        assert.equal(await page.locator('#ownmail-download-status').getAttribute('aria-live'), 'polite');
        state = {...state, has_progress: true, phase: 'checking', source: 'Primary'};
        await refresh();
        await waitStatus('Checking Primary for new mail');
        assert.equal(await counts.textContent(), '0 downloaded · 0 skipped · 0 failed');
        state = {...state, phase: 'downloading', downloaded: 7, skipped: 2};
        await refresh();
        await waitStatus('7 downloaded');
        assert.equal(await counts.textContent(), '7 downloaded · 2 skipped · 0 failed');
        assert.match(await page.locator('#ownmail-download-message').textContent(), /Downloading from Primary/);
        state = {...state, downloaded: 42, skipped: 3};
        await refresh();
        await waitStatus('42 downloaded');
        state = {...state, running: false, state: 'succeeded', finished_at: '2026-01-01T10:05:00Z'};
        await waitStatus('Download finished');
        assert.ok(await start.isEnabled());
        assert.equal(await counts.textContent(), '42 downloaded · 3 skipped · 0 failed');
        assert.equal(await page.locator('#ownmail-download-finished').textContent(),
            await page.evaluate(() => new Date('2026-01-01T10:05:00Z').toLocaleString()));
        startStatus = 503;
        await start.click();
        await waitStatus('Download process could not be started');
        assert.equal(await page.locator('#ownmail-download-message').textContent(), 'Download process could not be started.');
        assert.equal(await progress.isVisible(), false);
        assert.equal(await counts.textContent(), '');
        assert.equal(await error.isVisible(), false);
        assert.ok(await start.isEnabled());
        assert.equal(starts.length, 2);
        assert.equal(await page.locator('#brand_name').inputValue(), 'Unsaved appearance');
        assert.equal(settingsLoads, 1);
        assert.equal(await page.locator('#ownmail-loading-overlay').isVisible(), false);
        """,
    )


@pytest.mark.parametrize("has_progress", [True, False])
def test_finished_run_distinguishes_zero_new_mail_from_missing_progress(shell_app, download_browser, has_progress):
    app, _ = shell_app
    run_download_browser(
        app,
        download_browser,
        """
        state = {...state, state: 'succeeded', phase: 'finished', has_progress: __HAS_PROGRESS__};
        await refresh();
        await waitStatus(__HAS_PROGRESS__ ? 'No new mail.' : 'Download finished.');
        assert.equal(await progress.isVisible(), __HAS_PROGRESS__);
        assert.equal(await counts.textContent(), __HAS_PROGRESS__ ? '0 downloaded · 0 skipped · 0 failed' : '');
        """.replace("__HAS_PROGRESS__", json.dumps(has_progress)),
    )


def test_failure_reason_and_source_are_plain_text_and_clear_on_next_run(shell_app, download_browser):
    app, _ = shell_app
    run_download_browser(
        app,
        download_browser,
        """
        const source = '<img src=x onerror="window.unsafeSource = true">';
        const reason = 'Cannot sign in to <b>Primary</b>. Run ownmail setup to reconnect it.';
        state = {...state, state: 'running', running: true, has_progress: true, phase: 'authenticating',
            source, downloaded: 12, skipped: 1, errors: 0};
        await refresh();
        await waitStatus('Signing in to ' + source);
        assert.equal(await page.locator('#ownmail-download-status img').count(), 0);
        state = {...state, source: 'Secondary', errors: 1, failure_reason: reason};
        await refresh();
        await waitStatus('Signing in to Secondary');
        assert.equal(await page.locator('#ownmail-download-message').textContent(), 'Signing in to Secondary…');
        assert.equal(await counts.textContent(), '12 downloaded · 1 skipped · 1 failed');
        state = {...state, state: 'failed', running: false, phase: 'finished', errors: 1, failure_reason: reason};
        await refresh();
        await waitStatus(reason);
        assert.equal(await page.locator('#ownmail-download-message').textContent(), reason);
        assert.equal(await counts.textContent(), '12 downloaded · 1 skipped · 1 failed');
        assert.equal(await page.locator('#ownmail-download-status b').count(), 0);
        for (const [outcome, terminalReason] of [
            ['failed', 'Download failed. Check the server console.'],
            ['busy', 'Another download is already running.']
        ]) {
            state = {...state, state: outcome, failure_reason: terminalReason};
            await refresh();
            await waitStatus(terminalReason);
            assert.equal(await page.locator('#ownmail-download-message').textContent(), terminalReason);
        }
        await start.click();
        await waitStatus('Starting download');
        assert.equal(await counts.textContent(), '');
        assert.equal(await progress.isVisible(), false);
        assert.doesNotMatch(await page.locator('#ownmail-download-message').textContent(), /Cannot sign in/);
        state = {...state, has_progress: true, phase: 'checking', source: 'Primary'};
        await refresh();
        await waitStatus('Checking Primary');
        assert.equal(await counts.textContent(), '0 downloaded · 0 skipped · 0 failed');
        assert.equal(await page.evaluate(() => window.unsafeSource), undefined);
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
        state = {...state, running: true, state: 'running', phase: 'downloading', source: 'Personal archive',
            has_progress: true, downloaded: 42, skipped: 3, errors: 1,
            failure_reason: 'One message could not be downloaded.'};
        await refresh();
        await waitStatus('42 downloaded');
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
