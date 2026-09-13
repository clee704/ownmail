"""Navigation accessibility and browser interaction regressions."""

import json
import shutil
import struct
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lxml import html

from ownmail.sanitizer import HtmlSanitizer
from ownmail.web import create_app
from tests.conftest import mock_archive_db


@pytest.fixture
def shell_app(tmp_path):
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.auto_expire_trash.return_value = 0
    archive.search.return_value = []
    archive.db = mock_archive_db(
        get_label_counts={"Work": 3},
        get_role_counts={"inbox": 4, "trash": 1},
    )
    return create_app(archive), archive


@pytest.mark.parametrize(
    ("path", "destination"),
    [
        ("/search", "/"),
        ("/search?q=role%3Ainbox", "/search?q=role%3Ainbox&sort=date_desc"),
        ("/search?q=label%3A%22Work%22", "/search?q=label%3A%22Work%22&sort=date_desc"),
        ("/trash", "/trash"),
        ("/settings", "/settings"),
        ("/help", "/help"),
    ],
)
def test_navigation_announces_current_destination(shell_app, path, destination):
    app, _ = shell_app
    tree = html.fromstring(app.test_client().get(path).data)
    current = tree.xpath('//nav[@aria-label="Mail navigation"]//a[@aria-current="page"]')
    assert [link.get("href") for link in current] == [destination]


def test_many_labels_keep_full_names_and_utility_links(shell_app):
    app, archive = shell_app
    labels = {f"Project {i:03d} / Planning / Design & documentation": 1 for i in range(200)}
    archive.db.get_label_counts.return_value = labels
    tree = html.fromstring(app.test_client().get("/help").data)
    sidebar = tree.get_element_by_id("ownmail-sidebar")
    links = sidebar.xpath('.//ul[contains(@class, "ownmail-sidebar-labels")]//a')
    assert [link.get("aria-label") for link in links] == list(labels)
    assert all(link.get("title") == f"{link.get('aria-label')} — 1" for link in links)
    assert all(
        link.xpath('.//span[@class="ownmail-sidebar-label"]')[0].text == link.get("aria-label") for link in links
    )


def test_shell_utility_navigation_uses_sidebar(shell_app):
    app, _ = shell_app
    tree = html.fromstring(app.test_client().get("/help").data)
    assert not tree.xpath('//button[@aria-label="Application menu"]')
    footer = tree.xpath('//nav//ul[contains(@class, "ownmail-sidebar-footer")]')[0]
    assert [link.get("href") for link in footer.xpath(".//a")] == ["/settings", "/help"]


def test_home_screen_manifest_keeps_reader_and_utility_routes_in_scope(shell_app):
    app, _ = shell_app
    app.config["brand_name"] = "Archive Desk"
    client = app.test_client()
    page = html.fromstring(client.get("/search").data)
    manifest_link = page.xpath('/html/head/link[@rel="manifest"]')[0]
    response = client.get(manifest_link.get("href"))
    assert response.status_code == 200
    assert response.mimetype == "application/manifest+json"
    manifest = response.get_json()
    assert manifest["name"] == "Archive Desk"
    assert manifest["id"] == "/"
    assert manifest["start_url"] == "/search"
    assert manifest["display"] == "standalone"
    assert manifest["scope"] == "/", "Reader, Trash, and Settings must share the installed app's scope"


@pytest.mark.parametrize("path", ["/help", "/raw/message"])
def test_desktop_favicon_is_served_at_tab_sizes(shell_app, path):
    app, archive = shell_app
    (archive.archive_dir / "message.eml").write_text("Subject: Example\n\nExample message.")
    archive.db.get_email_by_id.return_value = ("message", "message.eml")
    client = app.test_client()
    page = html.fromstring(client.get(path).data)
    icon = page.xpath('/html/head/link[@rel="icon"]')[0]
    response = client.get(icon.get("href"))
    assert response.status_code == 200
    assert response.mimetype == "image/vnd.microsoft.icon"
    assert client.get("/favicon.ico").data == response.data
    assert struct.unpack_from("<HHH", response.data) == (0, 1, 3)
    sizes = set()
    for index in range(3):
        width, height, _, _, _, _, length, offset = struct.unpack_from("<BBBBHHII", response.data, 6 + 16 * index)
        png = response.data[offset : offset + length]
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack_from(">II", png, 16) == (width, height)
        sizes.add(f"{width}x{height}")
    assert sizes == set(icon.get("sizes").split()) == {"16x16", "32x32", "48x48"}


@pytest.mark.parametrize("path", ["/", "/search?q=annual", "/trash"])
def test_message_lists_indicate_attachments_with_accessible_text(shell_app, path):
    app, archive = shell_app
    rows = [
        (identifier, "message.eml", "Annual review", "sender@example.com", "2024-01-15", "Message body")
        for identifier in ["with-attachment", "without-attachment"]
    ]
    archive.search.return_value = [(*row, flag) for row, flag in zip(rows, [1, 0])]
    archive.db.get_trashed_emails.return_value = [
        (*row, "2024-01-16", "message.eml", flag) for row, flag in zip(rows, [1, 0])
    ]
    response = app.test_client().get(path, follow_redirects=True)
    assert response.status_code == 200
    tree = html.fromstring(response.data)
    rendered_rows = tree.xpath('//li[@class="ownmail-email-row"]')
    assert len(rendered_rows) == 2
    for row, has_attachments in zip(rendered_rows, [True, False]):
        link = row.xpath('.//a[@class="ownmail-email-row-link"]')[0]
        indicators = link.xpath('.//span[@class="ownmail-email-attachment"]')
        assert len(indicators) == int(has_attachments)
        if has_attachments:
            assert indicators[0].get("title") == "Has attachments"
            assert indicators[0].xpath('.//svg[@aria-hidden="true"]')
            description = tree.get_element_by_id(link.get("aria-describedby"))
            assert description.text_content() == "Has attachments"
        else:
            assert link.get("aria-describedby") is None


@pytest.fixture(scope="module")
def shell_browser():
    if not shutil.which("node"):
        pytest.skip("Node.js is unavailable")
    sanitizer = HtmlSanitizer()
    if not sanitizer._ensure_deps():
        pytest.skip("Browser test dependencies are unavailable")
    return Path(__file__).parents[1] / "ownmail" / "sanitizer"


def run_shell_browser(app, browser_dir, assertions, path="/help", theme=None):
    page = app.test_client().get(path).data.decode()
    script = """
const assert = require('node:assert/strict');
const { JSDOM, VirtualConsole } = require('jsdom');
const mediaQueries = new Map();
const scriptErrors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', error => scriptErrors.push(error.message));
const dom = new JSDOM(__PAGE__, {
    url: __URL__,
    runScripts: 'dangerously',
    virtualConsole,
    beforeParse(window) {
        window.localStorage.setItem('ownmail-sidebar', 'collapsed');
        if (__THEME__ !== null) window.localStorage.setItem('ownmail-theme', __THEME__);
        window.matchMedia = query => {
            if (!mediaQueries.has(query)) {
                mediaQueries.set(query, {
                    matches: false,
                    handlers: [],
                    addEventListener(type, handler) { this.handlers.push(handler); },
                    change(matches) {
                        this.matches = matches;
                        this.handlers.forEach(handler => handler({ matches }));
                    }
                });
            }
            return mediaQueries.get(query);
        };
    }
});
const { window } = dom;
const { document } = window;
const byId = id => document.getElementById(id);
const key = (target, name, shift = false) => target.dispatchEvent(
    new window.KeyboardEvent('keydown', { key: name, shiftKey: shift, bubbles: true, cancelable: true })
);
"""
    script = script.replace("__PAGE__", json.dumps(page)).replace("__URL__", json.dumps("http://localhost" + path))
    script = script.replace("__THEME__", json.dumps(theme))
    result = subprocess.run(
        ["node", "-e", script + assertions + "\nassert.deepEqual(scriptErrors, []);\ndom.window.close();\n"],
        cwd=browser_dir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_skip_link_targets_main_without_making_main_focusable(shell_app, shell_browser):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const skipLink = document.querySelector('.ownmail-skip-link');
const main = byId('ownmail-main');
assert.equal(document.querySelector(skipLink.getAttribute('href')), main);
skipLink.focus();
assert.equal(document.activeElement, skipLink);
main.focus();
assert.equal(document.activeElement, skipLink);
""",
    )


def test_mobile_navigation_focus_and_saved_desktop_width(shell_app, shell_browser):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const sidebar = byId('ownmail-sidebar');
const toggle = byId('ownmail-sidebar-toggle');
const breakpoint = mediaQueries.get('(max-width: 900px)');
assert(sidebar.classList.contains('collapsed'));
breakpoint.change(true);
assert.equal(toggle.getAttribute('aria-expanded'), 'false');
assert(sidebar.inert);
assert(!sidebar.classList.contains('collapsed'));
toggle.click();
assert.equal(toggle.getAttribute('aria-expanded'), 'true');
assert(!sidebar.inert);
assert(byId('ownmail-main').inert);
assert.equal(document.activeElement.getAttribute('href'), '/help');
const links = sidebar.querySelectorAll('a');
const last = links[links.length - 1];
last.focus();
key(last, 'Tab');
assert.equal(document.activeElement, toggle);
key(toggle, 'Tab', true);
assert.equal(document.activeElement, last);
key(last, 'Escape');
assert.equal(document.activeElement, toggle);
assert.equal(toggle.getAttribute('aria-expanded'), 'false');
assert(sidebar.inert);
assert(!byId('ownmail-main').inert);
breakpoint.change(false);
assert(sidebar.classList.contains('collapsed'));
assert(!sidebar.inert);
toggle.click();
assert(!sidebar.classList.contains('collapsed'));
assert.equal(window.localStorage.getItem('ownmail-sidebar'), 'expanded');
""",
    )


@pytest.mark.parametrize(("preference", "dark"), [("light", False), ("dark", True)])
def test_settings_theme_persists_and_overrides_system(shell_app, shell_browser, preference, dark):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const system = mediaQueries.get('(prefers-color-scheme: dark)');
let readerDark;
window.updateEmailDarkMode = dark => readerDark = dark;
const selected = byId('theme-' + PREFERENCE);
assert(selected.checked);
byId('theme-auto').click();
assert.equal(window.localStorage.getItem('ownmail-theme'), 'auto');
selected.click();
assert.equal(window.localStorage.getItem('ownmail-theme'), PREFERENCE);
assert.equal(document.documentElement.classList.contains('ownmail-dark'), DARK);
assert.equal(readerDark, DARK);
system.change(!DARK);
assert.equal(document.documentElement.classList.contains('ownmail-dark'), DARK);
assert.equal(readerDark, DARK);
""".replace("PREFERENCE", json.dumps(preference)).replace("DARK", json.dumps(dark)),
        path="/settings",
        theme=preference,
    )


def test_settings_system_theme_tracks_os_changes(shell_app, shell_browser):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const system = mediaQueries.get('(prefers-color-scheme: dark)');
assert(byId('theme-auto').checked);
assert(!document.documentElement.classList.contains('ownmail-dark'));
system.change(true);
assert(document.documentElement.classList.contains('ownmail-dark'));
byId('theme-light').click();
assert(!document.documentElement.classList.contains('ownmail-dark'));
byId('theme-auto').click();
assert.equal(window.localStorage.getItem('ownmail-theme'), 'auto');
assert(document.documentElement.classList.contains('ownmail-dark'));
system.change(false);
assert(!document.documentElement.classList.contains('ownmail-dark'));
""",
        path="/settings",
    )


@pytest.mark.parametrize("completion_event", ["load", "pageshow"])
def test_loading_overlay_waits_for_slow_navigation_and_cancels(shell_app, shell_browser, completion_event):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
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
const overlay = byId('ownmail-loading-overlay');
const visible = () => overlay.classList.contains('ownmail-active');
window.showLoading({metaKey: true});
window.showLoading({ctrlKey: true});
assert.equal(timers.size, 0);
const click = new window.MouseEvent('click', {cancelable: true});
window.showLoading(click);
assert(!click.defaultPrevented);
assert(!visible());
assert.equal(timers.size, 1);
advance(100);
window.showLoading();
assert.equal(nextTimer, 1);
advance(99);
assert(!visible());
advance(1);
assert(visible());
assert.equal(timers.size, 0);
window.showLoading();
assert.equal(nextTimer, 1);
window.dispatchEvent(new window.Event(COMPLETION_EVENT));
assert(!visible());
window.showLoading();
assert.equal(timers.size, 1);
advance(100);
window.dispatchEvent(new window.Event(COMPLETION_EVENT));
assert.equal(timers.size, 0);
advance(200);
assert(!visible());
window.showLoading();
advance(200);
assert(visible());
window.hideLoading();
assert(!visible());
""".replace("COMPLETION_EVENT", json.dumps(completion_event)),
    )


def test_list_sort_menu_submits_current_query_and_preserves_sort(shell_app, shell_browser):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const menu = byId('ownmail-list-menu');
const form = byId('ownmail-search-form');
let submitted;
form.requestSubmit = () => { submitted = new window.FormData(form); };
menu.open = true;
document.querySelector('input[value="date_asc"]').click();
assert.equal(submitted.get('sort'), 'date_asc');
assert.equal(submitted.get('q'), 'annual');
assert.equal(submitted.getAll('sort').length, 1);
assert(!menu.open);
byId('search-input').value = 'updated';
byId('search-input').dispatchEvent(new window.Event('input'));
assert.equal(new window.FormData(form).get('sort'), 'date_asc');
menu.open = true;
byId('relevance-option').click();
assert.equal(submitted.get('sort'), 'relevance');
assert.equal(submitted.get('q'), 'updated');
byId('search-input').value = '';
byId('search-input').dispatchEvent(new window.Event('input'));
assert(byId('relevance-option').disabled);
assert.equal(new window.FormData(form).get('sort'), 'date_desc');
menu.open = true;
key(menu.querySelector('summary'), 'Escape');
assert(!menu.open);
assert.equal(document.activeElement, menu.querySelector('summary'));
menu.open = true;
byId('search-input').click();
assert(!menu.open);
""",
        path="/search?q=annual",
    )


@pytest.fixture
def shell_list_app(shell_app):
    app, archive = shell_app
    rows = [
        (identifier, "message.eml", "Annual review", "sender@example.com", "2024-01-15", "Message body")
        for identifier in ["first", "second"]
    ]
    archive.search.return_value = [(*row, 0) for row in rows]
    archive.db.get_trashed_emails.return_value = [(*row, "2024-01-16", "message.eml", 0) for row in rows]
    return app


@pytest.mark.parametrize("path", ["/search", "/trash"])
def test_selection_replaces_list_controls_and_clear_restores_focus(shell_list_app, shell_browser, path):
    run_shell_browser(
        shell_list_app,
        shell_browser,
        """
const checkboxes = document.querySelectorAll('.ownmail-email-checkbox input');
const actions = byId('ownmail-toolbar-actions');
const controls = byId('ownmail-list-controls');
const selectAll = byId('ownmail-select-all');
const count = byId('ownmail-selection-count');
const list = byId('ownmail-email-list');
assert(!list.classList.contains('ownmail-selecting'));
assert(actions.hidden);
assert(!controls.hidden);
checkboxes[0].click();
assert.equal(count.textContent, '1 selected');
assert(!count.hidden);
assert(!actions.hidden);
assert(controls.hidden);
assert(byId('ownmail-refresh-results').hidden);
assert(selectAll.indeterminate);
assert(list.classList.contains('ownmail-selecting'));
selectAll.click();
assert.equal(count.textContent, '2 selected');
assert(Array.from(checkboxes).every(checkbox => checkbox.checked));
const clear = actions.querySelector('[aria-label="Clear selection"]');
clear.focus();
clear.click();
assert(actions.hidden);
assert(count.hidden);
assert(!controls.hidden);
assert(!byId('ownmail-refresh-results').hidden);
assert(!selectAll.checked);
assert(!selectAll.indeterminate);
assert(Array.from(checkboxes).every(checkbox => !checkbox.checked));
assert.equal(document.activeElement, selectAll);
assert(!list.classList.contains('ownmail-selecting'));
selectAll.click();
assert(list.classList.contains('ownmail-selecting'));
selectAll.click();
assert(!list.classList.contains('ownmail-selecting'));
""",
        path=path,
    )


def run_list_browser(app, browser_dir, assertions, path):
    run_shell_browser(
        app,
        browser_dir,
        """
let now = 0;
let nextTimer = 0;
const timers = new Map();
window.setTimeout = (callback, delay) => {
    timers.set(++nextTimer, {callback, deadline: now + delay});
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
function touch(target, type, touches = [{identifier: 1, clientX: 20, clientY: 20}]) {
    const event = new window.Event(type, {bubbles: true, cancelable: true});
    Object.defineProperty(event, 'touches', {value: touches});
    target.dispatchEvent(event);
    return event;
}
const list = byId('ownmail-email-list');
const rows = list.querySelectorAll('.ownmail-email-row');
const checkboxes = list.querySelectorAll('input[type="checkbox"]');
const mobile = mediaQueries.get('(max-width: 600px)');
mobile.change(true);
"""
        + assertions,
        path=path,
    )


@pytest.mark.parametrize("path", ["/search", "/trash"])
@pytest.mark.parametrize("target", [".ownmail-email-sender", ".ownmail-email-row-link", ".ownmail-email-row"])
def test_mobile_hold_selects_message_and_suppresses_navigation(shell_list_app, shell_browser, path, target):
    run_list_browser(
        shell_list_app,
        shell_browser,
        """
const target = list.querySelector(TARGET);
let clicks = 0;
target.addEventListener('click', event => { clicks++; event.preventDefault(); });
touch(target, 'touchstart');
advance(499);
assert(!checkboxes[0].checked);
const menu = new window.MouseEvent('contextmenu', {bubbles: true, cancelable: true});
target.dispatchEvent(menu);
assert(menu.defaultPrevented);
touch(target, 'touchmove', [{identifier: 1, clientX: 23, clientY: 24}]);
advance(1);
assert(checkboxes[0].checked);
assert(!checkboxes[1].checked);
assert(list.classList.contains('ownmail-selecting'));
assert.equal(byId('ownmail-selected-count').textContent, '1');
assert(touch(target, 'touchend', []).defaultPrevented);
const click = new window.MouseEvent('click', {bubbles: true, cancelable: true});
target.dispatchEvent(click);
assert(click.defaultPrevented);
assert.equal(clicks, 0);
assert(!byId('ownmail-loading-overlay').classList.contains('ownmail-active'));
checkboxes[0].click();
assert(!list.classList.contains('ownmail-selecting'));
""".replace("TARGET", json.dumps(target)),
        path,
    )


@pytest.mark.parametrize("path", ["/search", "/trash"])
@pytest.mark.parametrize("mobile", [True, False])
def test_short_taps_and_desktop_holds_preserve_links(shell_list_app, shell_browser, path, mobile):
    run_list_browser(
        shell_list_app,
        shell_browser,
        """
mobile.change(MOBILE);
for (const target of rows[0].querySelectorAll('a')) {
    let followed = false;
    target.addEventListener('click', event => {
        followed = !event.defaultPrevented;
        event.preventDefault();
    });
    touch(target, 'touchstart');
    advance(MOBILE ? 499 : 600);
    assert(!touch(target, 'touchend', []).defaultPrevented);
    target.dispatchEvent(new window.MouseEvent('click', {bubbles: true, cancelable: true}));
    assert(followed);
    assert(!checkboxes[0].checked);
}
assert(!list.classList.contains('ownmail-selecting'));
if (!MOBILE) {
    const menu = new window.MouseEvent('contextmenu', {bubbles: true, cancelable: true});
    rows[0].dispatchEvent(menu);
    assert(!menu.defaultPrevented);
}
""".replace("MOBILE", json.dumps(mobile)),
        path,
    )


@pytest.mark.parametrize("path", ["/search", "/trash"])
@pytest.mark.parametrize(
    "cancel",
    [
        "touch(target, 'touchmove', [{identifier: 1, clientX: 31, clientY: 20}]);",
        "touch(target, 'touchcancel', []);",
        "target.dispatchEvent(new window.Event('pointercancel', {bubbles: true}));",
        "list.dispatchEvent(new window.Event('scroll'));",
        "touch(document.body, 'touchstart', [{identifier: 1}, {identifier: 2}]);",
        "window.dispatchEvent(new window.Event('blur'));",
        "mobile.change(false);",
    ],
    ids=["movement", "touchcancel", "pointercancel", "scroll", "multitouch", "blur", "resize"],
)
def test_interrupted_mobile_hold_does_not_select(shell_list_app, shell_browser, path, cancel):
    run_list_browser(
        shell_list_app,
        shell_browser,
        """
const target = rows[0].querySelector('.ownmail-email-row-link');
touch(target, 'touchstart');
advance(400);
CANCEL
advance(200);
assert(!checkboxes[0].checked);
assert(!list.classList.contains('ownmail-selecting'));
assert(!touch(target, 'touchend', []).defaultPrevented);
""".replace("CANCEL", cancel),
        path,
    )


@pytest.mark.parametrize("path", ["/search", "/trash"])
@pytest.mark.parametrize("ending", ["touchend", "touchcancel", "pointercancel"])
def test_finished_mobile_hold_does_not_cancel_other_taps(shell_list_app, shell_browser, path, ending):
    run_list_browser(
        shell_list_app,
        shell_browser,
        """
const target = rows[0].querySelector('.ownmail-email-row-link');
touch(target, 'touchstart');
advance(500);
touch(target, ENDING, []);
assert(checkboxes[0].checked);
assert(!touch(byId('ownmail-select-all'), 'touchend', []).defaultPrevented);
if (ENDING === 'touchend') {
    touch(target, 'touchstart');
    advance(100);
    assert(!touch(target, 'touchend', []).defaultPrevented);
}
let followed = false;
target.addEventListener('click', event => {
    followed = !event.defaultPrevented;
    event.preventDefault();
});
target.dispatchEvent(new window.MouseEvent('click', {bubbles: true, cancelable: true}));
assert(followed);
""".replace("ENDING", json.dumps(ending)),
        path,
    )


@pytest.mark.parametrize("path", ["/search", "/trash"])
@pytest.mark.parametrize("disable_before_hold", [True, False])
def test_mobile_hold_respects_pending_message_actions(shell_list_app, shell_browser, path, disable_before_hold):
    run_list_browser(
        shell_list_app,
        shell_browser,
        """
checkboxes[0].disabled = DISABLE_BEFORE_HOLD;
touch(rows[0], 'touchstart');
advance(400);
checkboxes[0].disabled = true;
advance(100);
assert(!checkboxes[0].checked);
assert(!list.classList.contains('ownmail-selecting'));
assert(!touch(rows[0], 'touchend', []).defaultPrevented);
""".replace("DISABLE_BEFORE_HOLD", json.dumps(disable_before_hold)),
        path,
    )
