"""Navigation accessibility and browser interaction regressions."""

import json
import shutil
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
