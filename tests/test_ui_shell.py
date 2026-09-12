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
    footer = sidebar.xpath('./ul[contains(@class, "ownmail-sidebar-footer")]')[0]
    assert [link.get("href") for link in footer.xpath(".//a")] == ["/settings", "/help"]


@pytest.fixture(scope="module")
def shell_browser():
    if not shutil.which("node"):
        pytest.skip("Node.js is unavailable")
    sanitizer = HtmlSanitizer()
    if not sanitizer._ensure_deps():
        pytest.skip("Browser test dependencies are unavailable")
    return Path(__file__).parents[1] / "ownmail" / "sanitizer"


def run_shell_browser(app, browser_dir, assertions):
    page = app.test_client().get("/help").data.decode()
    script = """
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const mediaQueries = new Map();
const dom = new JSDOM(PAGE, {
    url: 'http://localhost/help',
    runScripts: 'dangerously',
    beforeParse(window) {
        window.localStorage.setItem('ownmail-sidebar', 'collapsed');
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
""".replace("PAGE", json.dumps(page))
    result = subprocess.run(
        ["node", "-e", script + assertions + "\ndom.window.close();\n"],
        cwd=browser_dir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


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


def test_application_menu_keyboard_and_theme(shell_app, shell_browser):
    app, _ = shell_app
    run_shell_browser(
        app,
        shell_browser,
        """
const button = byId('ownmail-hamburger-btn');
const menu = byId('ownmail-hamburger-dropdown');
assert.equal(button.getAttribute('aria-controls'), menu.id);
assert.equal(menu.getAttribute('role'), 'menu');
assert(menu.hidden);
button.focus();
key(button, 'ArrowDown');
assert.equal(button.getAttribute('aria-expanded'), 'true');
assert.equal(document.activeElement, menu.querySelector('button'));
key(document.activeElement, 'ArrowDown');
assert.equal(document.activeElement.getAttribute('href'), '/settings');
key(document.activeElement, 'End');
assert.equal(document.activeElement.getAttribute('href'), '/help');
key(document.activeElement, 'Escape');
assert(menu.hidden);
assert.equal(document.activeElement, button);
key(button, 'ArrowUp');
assert.equal(document.activeElement.getAttribute('href'), '/help');
key(document.activeElement, 'Home');
document.activeElement.click();
assert.equal(window.localStorage.getItem('ownmail-theme'), 'dark');
assert(document.documentElement.classList.contains('ownmail-dark'));
assert(menu.hidden);
assert.equal(document.activeElement, button);
""",
    )
