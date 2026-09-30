"""Session-only recovery with synthetic pages; physical Home Screen checks remain separate."""

import json
import subprocess
from pathlib import Path

import pytest

from tests import test_reader_navigation, test_ui_shell

reader = test_reader_navigation.reader
shell_browser = test_ui_shell.shell_browser
shell_app = test_ui_shell.shell_app
shell_list_app = test_ui_shell.shell_list_app
STATIC = Path(__file__).parents[1] / "ownmail" / "static"


def run_reading_state(reader, browser_dir, assertions, *, missing=False):
    client, archive = reader
    if missing:
        archive.db.get_email_by_id.return_value = None
    page = client.get("/email/message?return_to=%2Fsearch%3Fpage%3D3").data.decode()
    script = r"""
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const dom = new JSDOM(PAGE, {url:'http://localhost/email/message?return_to=%2Fsearch%3Fpage%3D3', runScripts:'outside-only'});
const {window} = dom;
const {document} = window;
const source = SOURCE;
const key = 'ownmail-reading-position';
const actions = document.getElementById('ownmail-reader-actions');
const position = {url: window.location.pathname + window.location.search,
    version: actions ? actions.dataset.readerVersion : 'old', scrollY: 640};
const frames = [];
let scrolled = [], loading = 0;
window.requestAnimationFrame = fn => frames.push(fn);
window.scrollTo = (x, y) => {scrolled.push([x,y]); window.scrollY = y;};
window.showLoading = () => loading++;
window.performance.getEntriesByType = () => [{type:'reload'}];
const save = value => window.sessionStorage.setItem(key, JSON.stringify(value));
const show = (persisted = false) => window.dispatchEvent(new window.PageTransitionEvent('pageshow', {persisted}));
const frame = () => {for (const fn of frames.splice(0)) fn();};
ASSERTIONS
dom.window.close();
"""
    script = script.replace("PAGE", json.dumps(page)).replace(
        "SOURCE", json.dumps((STATIC / "result-state.js").read_text())
    )
    result = subprocess.run(
        ["node", "-e", script.replace("ASSERTIONS", assertions)],
        cwd=browser_dir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_same_reader_reload_restores_once_and_background_saves_only_position(reader, shell_browser):
    run_reading_state(
        reader,
        shell_browser,
        """
save(position);
window.eval(source);
show(); frame(); frame();
assert.deepEqual(scrolled, [[0,640]]);
window.scrollY = 920;
Object.defineProperty(document, 'visibilityState', {value:'hidden'});
document.dispatchEvent(new window.Event('visibilitychange'));
assert.deepEqual(JSON.parse(window.sessionStorage.getItem(key)), {...position, scrollY:920});
window.scrollY = 1000;
window.dispatchEvent(new window.PageTransitionEvent('pagehide'));
assert.deepEqual(JSON.parse(window.sessionStorage.getItem(key)), {...position, scrollY:1000});
show(true); frame(); frame();
assert.deepEqual(scrolled, [[0,640]], 'Native cached-page restoration must not be replaced');
""",
    )


@pytest.mark.parametrize(
    "changed",
    [
        "position.url = '/email/other'",
        "position.version = 'old'",
        "position.scrollY = -1",
        "position.scrollY = '640'",
        "position.scrollY = null",
        "position.scrollY = 1e309",
        "window.location.hash = '#paragraph'",
        "window.scrollY = 80",
        "window.performance.getEntriesByType = () => [{type:'back_forward'}]",
    ],
)
def test_stale_invalid_or_native_reading_positions_are_not_overridden(reader, shell_browser, changed):
    run_reading_state(
        reader,
        shell_browser,
        changed
        + """;
save(position); window.eval(source); show(); frame(); frame();
assert.deepEqual(scrolled, []);
""",
    )


@pytest.mark.parametrize("interaction", ["wheel", "touchstart", "pointerdown", "keydown"])
def test_reading_restore_does_not_override_new_user_movement(reader, shell_browser, interaction):
    run_reading_state(
        reader,
        shell_browser,
        """
save(position); window.eval(source); show();
window.dispatchEvent(new window.Event(INTERACTION));
frame(); frame();
assert.deepEqual(scrolled, []);
""".replace("INTERACTION", json.dumps(interaction)),
    )


def test_unavailable_reader_discards_stale_position_without_losing_return_link(reader, shell_browser):
    run_reading_state(
        reader,
        shell_browser,
        """
save(position); window.eval(source);
assert.equal(window.sessionStorage.getItem(key), null);
assert.equal(document.getElementById('ownmail-back-to-results').pathname, '/search');
""",
        missing=True,
    )


def test_storage_denial_does_not_break_reader_navigation(reader, shell_browser):
    run_reading_state(
        reader,
        shell_browser,
        """
Object.defineProperty(window, 'sessionStorage', {get() {throw Error('blocked');}});
window.eval(source); show(); frame(); frame();
window.dispatchEvent(new window.PageTransitionEvent('pagehide'));
assert.deepEqual(scrolled, []);
""",
    )


def test_theme_metadata_refreshes_on_resume_and_cross_tab_change(shell_app, shell_browser):
    app, _ = shell_app
    test_ui_shell.run_shell_browser(
        app,
        shell_browser,
        """
const meta = document.head.querySelector('meta[name="theme-color"]');
assert.equal(meta.content, '#ffffff');
window.localStorage.setItem('ownmail-theme', 'dark');
window.dispatchEvent(new window.PageTransitionEvent('pageshow', {persisted:true}));
assert.equal(meta.content, '#202124');
window.localStorage.setItem('ownmail-theme', 'light');
window.dispatchEvent(new window.StorageEvent('storage', {key:'ownmail-theme'}));
assert.equal(meta.content, '#ffffff');
""",
    )


NAVIGATION_CLOCK = """
let now = 0, nextTimer = 0, stopped = 0;
const timers = new Map();
window.setTimeout = (fn, delay) => {timers.set(++nextTimer, {fn, at:now+delay}); return nextTimer;};
window.clearTimeout = id => timers.delete(id);
window.stop = () => stopped++;
const advance = ms => {
    now += ms;
    for (const [id, timer] of timers) if (timer.at <= now) {timers.delete(id); timer.fn();}
};
const feedback = byId('ownmail-action-feedback');
const retry = byId('ownmail-action-retry');
const rows = document.querySelectorAll('.ownmail-email-row-link');
const start = target => window.showLoading({target, button:0});
"""


def test_navigation_deadline_clears_spinner_and_offers_exact_get_retry(shell_list_app, shell_browser):
    test_ui_shell.run_shell_browser(
        shell_list_app,
        shell_browser,
        NAVIGATION_CLOCK
        + """
start(rows[0]);
advance(200);
assert(rows[0].closest('li').classList.contains('ownmail-loading'));
advance(29800);
assert.equal(stopped, 1);
assert(!rows[0].closest('li').classList.contains('ownmail-loading'));
assert(!byId('ownmail-loading-overlay').classList.contains('ownmail-active'));
assert.equal(byId('ownmail-loading-status').textContent, '');
assert.equal(feedback.dataset.state, 'error');
assert(!retry.hidden);
assert.equal(retry.href, rows[0].href);
assert.equal(timers.size, 0);
assert.equal(window.location.pathname, '/search');
""",
        path="/search",
    )


@pytest.mark.parametrize("completion", ["load", "pageshow", "pagehide", "escape", "replacement"])
def test_abandoned_navigation_cannot_announce_a_late_failure(shell_list_app, shell_browser, completion):
    test_ui_shell.run_shell_browser(
        shell_list_app,
        shell_browser,
        NAVIGATION_CLOCK
        + """
start(rows[0]); advance(200);
if (COMPLETION === 'escape') {
    document.dispatchEvent(new window.KeyboardEvent('keydown', {key:'Escape'}));
} else if (COMPLETION === 'replacement') {
    start(rows[1]); advance(200);
    window.dispatchEvent(new window.Event('pagehide'));
} else window.dispatchEvent(new window.Event(COMPLETION));
advance(30000);
assert(feedback.hidden);
assert.equal(stopped, COMPLETION === 'escape' ? 1 : 0);
assert.equal(timers.size, 0);
""".replace("COMPLETION", json.dumps(completion)),
        path="/search",
    )


@pytest.mark.parametrize("method", ["get", "post"])
def test_form_recovery_preserves_get_query_but_never_repeats_post(shell_app, shell_browser, method):
    app, _ = shell_app
    test_ui_shell.run_shell_browser(
        app,
        shell_browser,
        NAVIGATION_CLOCK
        + """
const form = document.querySelector('.ownmail-search-form');
form.method = METHOD;
byId('search-input').value = 'label:Project annual';
start(form); advance(30000);
assert.equal(stopped, 1);
assert(!retry.hidden);
assert.equal(retry.pathname, METHOD === 'get' ? '/search' : '/help');
assert.equal(retry.search, METHOD === 'get' ? '?q=label%3AProject+annual' : '');
assert.equal(form.method, METHOD);
""".replace("METHOD", json.dumps(method)),
    )


def test_latest_utility_navigation_owns_the_retry_destination(shell_app, shell_browser):
    app, _ = shell_app
    test_ui_shell.run_shell_browser(
        app,
        shell_browser,
        NAVIGATION_CLOCK
        + """
start(document.querySelector('#ownmail-sidebar a[href="/settings"]'));
advance(200);
start(document.querySelector('#ownmail-sidebar a[href="/help"]'));
advance(30000);
assert.equal(retry.pathname, '/help');
assert.equal(stopped, 1);
assert.equal(timers.size, 0);
""",
    )
