"""Message actions retain context until the server confirms an outcome."""

import json
import subprocess
from pathlib import Path

import pytest
from flask import render_template
from lxml import html

from tests import test_ui_shell

shell_app = test_ui_shell.shell_app
shell_browser = test_ui_shell.shell_browser

ACTION_SCRIPT = Path(__file__).parents[1] / "ownmail" / "static" / "message-actions.js"


def run_action_script(browser_dir, assertions, page=None):
    page = (
        page
        or """
        <button data-message-action>Move to trash</button>
        <label class="ownmail-email-checkbox"><input type="checkbox" checked value="message"></label>
        <div id="ownmail-action-feedback" hidden><span id="ownmail-action-message"></span>
            <button id="ownmail-action-dismiss">Dismiss</button></div>
    """
    )
    script = """
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(PAGE, { url: 'http://localhost/search?q=project&page=2', runScripts: 'outside-only' });
const { window } = dom;
const { document } = window;
const source = SOURCE;
const feedback = document.getElementById('ownmail-action-feedback');
const checkbox = document.querySelector('.ownmail-email-checkbox input');
const button = document.querySelector('[data-message-action]');
let now = 0;
let nextTimer = 0;
const timers = new Map();
window.setTimeout = (callback, delay) => {
    timers.set(++nextTimer, { callback, deadline: now + delay });
    return nextTimer;
};
window.clearTimeout = id => timers.delete(id);
function advance(milliseconds) {
    now += milliseconds;
    for (const [id, timer] of timers) {
        if (timer.deadline <= now) {
            timers.delete(id);
            timer.callback();
        }
    }
}
let cleaned = 0;
window.hideLoading = () => cleaned++;
window.eval(source);
const action = {
    url: '/trash-bulk', request: { method: 'POST', body: 'ids=message' },
    pending: 'Moving messages to trash…', success: 'Messages moved to trash.',
    failure: 'Could not move messages to trash.'
};
const timeout = setTimeout(() => { console.error('Browser assertions did not finish'); process.exit(1); }, 5000);
(async () => {
ASSERTIONS
})().then(() => { clearTimeout(timeout); dom.window.close(); }).catch(error => {
    clearTimeout(timeout); console.error(error); process.exitCode = 1;
});
"""
    script = script.replace("PAGE", json.dumps(page)).replace("SOURCE", json.dumps(ACTION_SCRIPT.read_text()))
    result = subprocess.run(
        ["node", "-e", script.replace("ASSERTIONS", assertions)],
        cwd=browser_dir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_pending_action_waits_for_confirmation_and_rejects_duplicates(shell_browser):
    run_action_script(
        shell_browser,
        """
let resolve;
let requests = 0;
let success = 0;
window.fetch = () => { requests++; return new Promise(done => resolve = done); };
action.onSuccess = () => success++;
const pending = window.ownmailMessageAction(action);
assert.equal(feedback.dataset.state, 'pending');
assert(button.disabled);
assert(checkbox.disabled);
assert.equal(success, 0);
const duplicate = window.ownmailMessageAction(action);
assert.equal(requests, 1);
assert.equal(await duplicate, false);
advance(10000);
assert(!feedback.hidden);
resolve({ ok: true });
assert.equal(await pending, true);
assert.equal(success, 1);
assert.equal(feedback.dataset.state, 'success');
assert(!button.disabled);
assert(!checkbox.disabled);
assert.equal(cleaned, 1);
""",
    )


@pytest.mark.parametrize(
    "failure", ["Promise.resolve({ok: false, status: 503})", "Promise.reject(new Error('offline'))"]
)
def test_failed_action_retains_selection_and_can_retry(shell_browser, failure):
    run_action_script(
        shell_browser,
        """
let navigated = false;
action.navigate = () => navigated = true;
window.fetch = () => FAILURE;
assert.equal(await window.ownmailMessageAction(action), false);
assert.equal(feedback.dataset.state, 'error');
assert.equal(feedback.getAttribute('role'), 'alert');
assert(feedback.textContent.includes('Try the action again.'));
assert(!button.disabled);
assert(checkbox.checked);
assert(!checkbox.disabled);
assert(!navigated);
assert.equal(window.location.search, '?q=project&page=2');
assert.equal(window.sessionStorage.getItem('ownmail-action-notice'), null);
assert.equal(cleaned, 1);
advance(10000);
assert(!feedback.hidden);
window.fetch = () => Promise.resolve({ok: true});
assert.equal(await window.ownmailMessageAction(action), true);
assert(navigated);
""".replace("FAILURE", failure),
    )


def test_success_feedback_disappears_after_four_seconds_without_moving_focus(shell_browser):
    run_action_script(
        shell_browser,
        """
window.fetch = () => Promise.resolve({ok: true});
action.success = 'Sender trusted.';
await window.ownmailMessageAction(action);
button.focus();
advance(3999);
assert(!feedback.hidden);
assert.equal(document.getElementById('ownmail-action-message').textContent, 'Sender trusted.');
advance(1);
assert(feedback.hidden);
assert.equal(document.activeElement, button);
""",
    )


def test_new_action_cancels_previous_feedback_timeout(shell_browser):
    run_action_script(
        shell_browser,
        """
window.fetch = () => Promise.resolve({ok: true});
await window.ownmailMessageAction(action);
advance(3000);
let resolve;
window.fetch = () => new Promise(done => resolve = done);
const pending = window.ownmailMessageAction(action);
advance(1000);
assert.equal(feedback.dataset.state, 'pending');
assert(!feedback.hidden);
resolve({ok: true});
await pending;
advance(3999);
assert(!feedback.hidden);
advance(1);
assert(feedback.hidden);
""",
    )


def test_manual_feedback_dismissal_clears_timeout(shell_browser):
    run_action_script(
        shell_browser,
        """
window.fetch = () => Promise.resolve({ok: true});
await window.ownmailMessageAction(action);
document.getElementById('ownmail-action-dismiss').click();
assert(feedback.hidden);
assert.equal(timers.size, 0);
""",
    )


def test_confirmed_notice_survives_navigation_once(shell_browser):
    run_action_script(
        shell_browser,
        """
window.fetch = () => Promise.resolve({ok: true});
action.navigate = () => {};
await window.ownmailMessageAction(action);
assert(window.sessionStorage.getItem('ownmail-action-notice'));
feedback.hidden = true;
window.eval(source);
assert(!feedback.hidden);
assert.equal(feedback.dataset.state, 'success');
assert.equal(document.getElementById('ownmail-action-message').textContent, action.success);
assert.equal(window.sessionStorage.getItem('ownmail-action-notice'), null);
advance(4000);
assert(feedback.hidden);
window.eval(source);
assert(feedback.hidden);
""",
    )


def test_unavailable_session_storage_does_not_block_action(shell_browser):
    run_action_script(
        shell_browser,
        """
Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('storage disabled'); } });
window.eval(source);
window.fetch = () => Promise.resolve({ok: true});
let navigated = false;
action.navigate = () => navigated = true;
assert.equal(await window.ownmailMessageAction(action), true);
assert(navigated);
assert.equal(feedback.dataset.state, 'success');
""",
    )


@pytest.mark.parametrize(
    ("path", "heading", "next_action"),
    [
        ("/search", "No archived mail yet", "https://github.com/clee704/ownmail#quick-start"),
        ("/search?q=missing", 'No results found for "missing"', "/"),
        ("/trash", "Trash is empty", "/"),
    ],
)
def test_empty_views_explain_state_and_offer_next_action(shell_app, path, heading, next_action):
    app, _ = shell_app
    tree = html.fromstring(app.test_client().get(path).data)
    state = tree.xpath('//div[@class="ownmail-no-results"]')[0]
    assert state.find("h3").text == heading
    assert state.find("p").text
    assert state.xpath('.//a[@class="ownmail-empty-action"]')[0].get("href") == next_action


@pytest.mark.parametrize(
    ("template", "call", "endpoint", "body", "confirmation"),
    [
        ("search.html", "trashSelected()", "/trash-bulk", "ids=message", "Move 1 email(s) to trash?"),
        ("trash.html", "restoreSelected()", "/restore-bulk", "ids=message", None),
        (
            "trash.html",
            "deleteForeverSelected()",
            "/delete-forever",
            "ids=message",
            "Permanently delete 1 email(s)? This cannot be undone.",
        ),
        (
            "trash.html",
            "emptyTrash({preventDefault() {}})",
            "/empty-trash",
            None,
            "Permanently delete all 1 email(s) in trash? This cannot be undone.",
        ),
        ("email.html", "trashEmail('message')", "/trash/message", None, "Move this email to trash?"),
        ("email.html", "restoreEmail('message')", "/restore/message", None, None),
        (
            "email.html",
            "deleteForever('message')",
            "/delete-forever",
            "ids=message",
            "Permanently delete this email? This cannot be undone.",
        ),
        ("email.html", "trustSender()", "/trust-sender", "email=sender%40example.com", None),
        ("email.html", "untrustSender()", "/untrust-sender", "email=sender%40example.com", None),
    ],
)
def test_existing_action_requests_and_confirmations(
    shell_app, shell_browser, template, call, endpoint, body, confirmation
):
    app, _ = shell_app
    with app.test_request_context("/search"):
        page = render_template(
            template,
            results=[{"email_id": "message", "subject": "Synthetic", "sender_name": "Sender"}],
            query="",
            start_idx=0,
            trash_count=1,
            subject="Synthetic",
            sender_email="sender@example.com",
            has_external_images=True,
            images_blocked=True,
            body_text="Synthetic message.",
        )
    run_action_script(
        shell_browser,
        """
window.matchMedia = () => ({matches: false, addEventListener() {}});
window.scrollTo = () => {};
for (const script of document.querySelectorAll('script:not([src])')) window.eval(script.textContent);
if (checkbox) checkbox.checked = true;
let captured;
let confirmations = [];
window.confirm = message => { confirmations.push(message); return true; };
window.ownmailMessageAction = input => captured = input;
window.eval(CALL);
assert.equal(captured.url, ENDPOINT);
assert.equal(captured.request.method, 'POST');
assert.equal(captured.request.body || null, BODY);
assert.deepEqual(confirmations, CONFIRMATION === null ? [] : [CONFIRMATION]);
if (CONFIRMATION !== null) {
    captured = undefined;
    window.confirm = () => false;
    window.eval(CALL);
    assert.equal(captured, undefined);
}
""".replace("CALL", json.dumps(call))
        .replace("ENDPOINT", json.dumps(endpoint))
        .replace("BODY", json.dumps(body))
        .replace("CONFIRMATION", json.dumps(confirmation)),
        page=page,
    )
