"""Archived-label editing against synthetic responses in a real browser."""

import json
import subprocess

import pytest
from flask import render_template
from lxml import html

from tests import test_email_contrast, test_ui_shell

shell_app = test_ui_shell.shell_app
label_browser = test_email_contrast.contrast_browser


def run_label_browser(app, node, assertions, *, labels=("Work",), viewport=(1100, 900)):
    with app.test_request_context("/email/synthetic"):
        page = render_template(
            "email.html",
            email_id="synthetic",
            subject="Project planning",
            sender="sender@example.com",
            date="2026-01-01",
            body_text="A synthetic archived message for label editing.",
        )
    client = app.test_client()
    files = {}
    for path in html.fromstring(page).xpath('//script[@src]/@src | //link[@rel="stylesheet"]/@href'):
        response = client.get(path)
        assert response.status_code == 200, path
        files[path] = {"body": response.data.decode(), "contentType": response.mimetype}
    payload = {
        "page": page,
        "files": files,
        "labels": labels,
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
        const page = await browser.newPage({viewport: input.viewport});
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        let getPayload = {labels: input.labels};
        let getStatus = 200;
        let getOffline = false;
        let getGate = null;
        let postPayload = {indexed: true};
        let postStatus = 200;
        let postOffline = false;
        let postInvalidJSON = false;
        let postGate = null;
        let pageLoads = 0;
        let gets = 0;
        const posts = [];
        await page.route('**/*', async route => {
            const request = route.request();
            const url = new URL(request.url());
            if (url.origin !== 'http://ownmail.test') return route.abort();
            if (url.pathname === '/email/synthetic') {
                pageLoads++;
                return route.fulfill({contentType: 'text/html', body: input.page});
            }
            if (input.files[url.pathname]) return route.fulfill(input.files[url.pathname]);
            if (url.pathname === '/labels/synthetic' && request.method() === 'GET') {
                gets++;
                const body = JSON.stringify(getPayload);
                const status = getStatus;
                if (getGate) await getGate;
                if (getOffline) return route.abort();
                return route.fulfill({status, contentType: 'application/json', body});
            }
            if (url.pathname === '/labels/synthetic' && request.method() === 'POST') {
                posts.push(request.postDataJSON());
                if (postGate) await postGate;
                if (postOffline) return route.abort();
                if (postInvalidJSON) return route.fulfill({contentType: 'application/json', body: '{'});
                return route.fulfill({status: postStatus, json: postPayload});
            }
            return route.abort();
        });
        await page.addInitScript(() => {
            localStorage.setItem('ownmail-theme', 'light');
            localStorage.setItem('ownmail-sidebar', 'collapsed');
        });
        await page.goto('http://ownmail.test/email/synthetic', {waitUntil: 'load'});
        const menu = page.locator('summary[aria-label="More message actions"]');
        const trigger = page.locator('#ownmail-edit-labels');
        const editor = page.locator('#ownmail-label-editor');
        const inputBox = page.locator('#ownmail-label-input');
        const add = page.locator('#ownmail-label-add');
        const save = page.locator('#ownmail-label-save');
        const close = page.locator('#ownmail-label-close');
        const status = page.locator('#ownmail-label-status');
        const names = () => page.locator('#ownmail-label-items li span').allTextContents();
        const waitStatus = text => page.waitForFunction(text =>
            document.getElementById('ownmail-label-status').textContent.includes(text), text);
        const waitLoaded = () => page.waitForFunction(() =>
            !document.getElementById('ownmail-label-input').disabled);
        const open = async () => {
            await menu.click();
            await trigger.click();
        };
        const addLabel = async text => {
            await inputBox.fill(text);
            await add.click();
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
        input=json.dumps(payload),
        cwd=test_email_contrast.SANITIZER_DIR,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


def test_open_and_edit_preserves_raw_label_text_and_focus(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        r"""
        assert.equal(await editor.isVisible(), false);
        await open();
        await waitLoaded();
        assert.equal(await trigger.getAttribute('aria-expanded'), 'true');
        assert.equal(await inputBox.evaluate(element => element === document.activeElement), true);
        assert.deepEqual(await names(), input.labels);
        assert.equal(await page.locator('#ownmail-label-items img').count(), 0);
        assert.equal(await page.evaluate(() => window.labelInjected), undefined);
        assert.equal(await page.locator('#ownmail-label-history').isVisible(), true);
        const added = '  New / label, "quoted"  ';
        await inputBox.fill(added);
        await inputBox.press('Enter');
        assert.deepEqual(await names(), [...input.labels, added]);
        assert.equal(await inputBox.inputValue(), '');
        await page.locator('#ownmail-label-items button').first().click();
        assert.deepEqual(await names(), [...input.labels.slice(1), added]);
        assert.equal(await page.locator('#ownmail-label-items button').first().evaluate(
            element => element === document.activeElement), true);
        await close.click();
        assert.equal(await editor.isVisible(), false);
        assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
        assert.equal(await menu.evaluate(element => element === document.activeElement), true);
        assert.deepEqual(posts, []);
        """,
        labels=('  Team / A,B : "x"  ', '<img src=x onerror="window.labelInjected=true">', "INBOX", "UNREAD"),
    )


def test_validation_keeps_pending_text_and_can_save_an_empty_label_list(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        await open();
        await waitLoaded();
        await save.click();
        await waitStatus('Remove UNREAD before saving');
        assert.equal(await status.getAttribute('role'), 'alert');
        assert.deepEqual(await names(), ['Work', 'UNREAD']);
        assert.deepEqual(posts, []);
        await page.locator('#ownmail-label-items button[aria-label="Remove label UNREAD"]').click();
        await addLabel('   ');
        await waitStatus('Enter a label name.');
        await addLabel('UNREAD');
        await waitStatus('cannot be saved');
        await addLabel('Work');
        await waitStatus('already present');
        assert.deepEqual(await names(), ['Work']);
        await inputBox.fill('Not added yet');
        await save.click();
        await waitStatus('Add the entered label');
        assert.equal(await inputBox.inputValue(), 'Not added yet');
        assert.equal(await inputBox.evaluate(element => element === document.activeElement), true);
        assert.deepEqual(posts, []);
        await inputBox.fill('');
        await page.locator('#ownmail-label-items button').click();
        assert.equal(await page.locator('#ownmail-label-empty').isVisible(), true);
        assert.equal(await inputBox.evaluate(element => element === document.activeElement), true);
        const reloaded = page.waitForEvent('load');
        await save.click();
        await reloaded;
        assert.deepEqual(posts, [{labels: []}]);
        assert.equal(pageLoads, 2);
        assert.equal(await editor.isVisible(), false);
        """,
        labels=("Work", "UNREAD"),
    )


def test_pending_save_disables_controls_and_prevents_duplicate_submission(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        await open();
        await waitLoaded();
        await addLabel('New label');
        let release;
        postGate = new Promise(resolve => release = resolve);
        await save.evaluate(button => {button.click(); button.click();});
        await waitStatus('Saving labels');
        await page.waitForTimeout(100);
        assert.deepEqual(posts, [{labels: ['Work', 'New label']}]);
        for (const control of [trigger, inputBox, add, save, close,
                page.locator('#ownmail-label-items button').first()]) {
            assert.equal(await control.isDisabled(), true);
        }
        await page.locator('#ownmail-label-form').evaluate(form =>
            form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
        assert.equal(posts.length, 1);
        assert.equal(await editor.isVisible(), true);
        const reloaded = page.waitForEvent('load');
        release();
        await reloaded;
        assert.equal(pageLoads, 2);
        assert.equal(await editor.isVisible(), false);
        """,
    )


@pytest.mark.parametrize("failure", ["postStatus = 503", "postOffline = true", "postInvalidJSON = true"])
def test_failed_save_keeps_draft_labels_and_allows_retry(shell_app, label_browser, failure):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        await open();
        await waitLoaded();
        await addLabel('Draft edit');
        __FAILURE__;
        await save.click();
        await waitStatus('Could not confirm');
        assert.equal(await status.getAttribute('role'), 'alert');
        assert.deepEqual(await names(), ['Work', 'Draft edit']);
        assert.equal(await save.isEnabled(), true);
        assert.equal(await inputBox.isEnabled(), true);
        assert.equal(pageLoads, 1);
        postStatus = 200;
        postOffline = postInvalidJSON = false;
        const reloaded = page.waitForEvent('load');
        await save.click();
        await reloaded;
        assert.deepEqual(posts, [
            {labels: ['Work', 'Draft edit']}, {labels: ['Work', 'Draft edit']}
        ]);
        assert.equal(pageLoads, 2);
        """.replace("__FAILURE__", failure),
    )


def test_partial_save_keeps_search_warning_visible_until_retry(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        await open();
        await waitLoaded();
        await addLabel('Saved locally');
        postPayload = {indexed: false};
        await save.click();
        await waitStatus('Labels saved. Search could not be updated. Save again to retry.');
        assert.equal(await status.getAttribute('role'), 'alert');
        await page.waitForTimeout(4200);
        assert.equal(await status.isVisible(), true);
        assert.match(await status.textContent(), /Labels saved.*Search could not be updated/);
        assert.deepEqual(await names(), ['Work', 'Saved locally']);
        assert.equal(await save.isEnabled(), true);
        assert.equal(pageLoads, 1);
        postPayload = {indexed: true};
        const reloaded = page.waitForEvent('load');
        await save.click();
        await reloaded;
        assert.equal(pageLoads, 2);
        assert.deepEqual(posts, [
            {labels: ['Work', 'Saved locally']}, {labels: ['Work', 'Saved locally']}
        ]);
        """,
    )


@pytest.mark.parametrize("failure", ["getStatus = 503", "getOffline = true", "getPayload = {labels: [1]}"])
def test_load_failure_keeps_save_disabled_and_reopening_retries(shell_app, label_browser, failure):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        __FAILURE__;
        await open();
        await waitStatus('Close the editor and try again.');
        assert.equal(await status.getAttribute('role'), 'alert');
        assert.equal(await save.isDisabled(), true);
        assert.equal(await inputBox.isDisabled(), true);
        assert.equal(await close.isEnabled(), true);
        await close.click();
        getStatus = 200;
        getOffline = false;
        getPayload = {labels: ['Retry labels']};
        await open();
        await waitLoaded();
        assert.deepEqual(await names(), ['Retry labels']);
        assert.equal(gets, 2);
        assert.deepEqual(posts, []);
        """.replace("__FAILURE__", failure),
    )


def test_closing_during_loading_ignores_the_late_response_after_reopening(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        let release;
        getGate = new Promise(resolve => release = resolve);
        await open();
        await waitStatus('Loading labels');
        assert.equal(await close.evaluate(element => element === document.activeElement), true);
        await close.click();
        assert.equal(await editor.isVisible(), false);
        getGate = null;
        getPayload = {labels: ['Current labels']};
        await open();
        await waitLoaded();
        assert.deepEqual(await names(), ['Current labels']);
        const late = page.waitForResponse(response => new URL(response.url()).pathname === '/labels/synthetic');
        release();
        await late;
        await page.waitForTimeout(100);
        assert.deepEqual(await names(), ['Current labels']);
        assert.equal(await inputBox.evaluate(element => element === document.activeElement), true);
        assert.equal(await editor.isVisible(), true);
        assert.equal(gets, 2);
        """,
    )


def test_narrow_editor_wraps_long_names_without_horizontal_overflow(shell_app, label_browser):
    app, _ = shell_app
    run_label_browser(
        app,
        label_browser,
        """
        await open();
        await waitLoaded();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
        assert.equal(await editor.evaluate(element => element.scrollWidth <= element.clientWidth), true);
        for (const control of [inputBox, add, save, close]) {
            assert.ok((await control.boundingBox()).height >= 44);
        }
        assert.deepEqual(await names(), input.labels);
        await page.screenshot({path: '/tmp/ownmail-label-editor-mobile.png', fullPage: true});
        """,
        labels=("Planning / " + "VeryLongLabel" * 20, '  raw, "quoted" label  '),
        viewport=(375, 900),
    )
