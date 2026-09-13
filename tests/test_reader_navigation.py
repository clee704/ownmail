"""Message navigation and metadata remain usable in the compact reader."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lxml import html

from ownmail.web import create_app
from tests import test_ui_shell
from tests.conftest import mock_archive_db

shell_browser = test_ui_shell.shell_browser


@pytest.fixture
def reader(tmp_path):
    (tmp_path / "message.eml").write_text(
        "From: Alex Sender <alex@example.com>\n"
        "To: Pat Reader <pat@example.com>, Lee Reader <lee@example.com>\n"
        "Subject: A message with full recipient details\n"
        "Date: Mon, 15 Jan 2024 10:30:00 +0000\n"
        "Content-Type: text/plain\n\n"
        "The message body remains visible.\n"
    )
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.db = mock_archive_db()
    archive.db.get_email_by_id.return_value = ("message", "message.eml", None, None, None, None)
    archive.db.get_labels_for_email.return_value = ["Project planning", "Review"]
    app = create_app(archive)
    with app.test_client() as client:
        yield client, archive


def back_href(response):
    assert response.status_code == 200
    document = html.fromstring(response.data)
    return document.get_element_by_id("ownmail-back-to-results").get("href")


@pytest.mark.parametrize("destination", ["/search?q=label%3AReview+annual&sort=date_asc&page=3", "/trash"])
def test_explicit_return_preserves_result_context(reader, destination):
    client, _ = reader
    response = client.get(
        "/email/message",
        query_string={"return_to": destination},
        headers={"Referer": "http://localhost/search?q=different"},
    )
    assert back_href(response) == destination


@pytest.mark.parametrize("trashed", [False, True])
def test_direct_message_has_local_list_fallback(reader, trashed):
    client, archive = reader
    archive.db.get_email_by_id.return_value = (
        "message",
        "message.eml",
        None,
        None,
        None,
        "2024-01-16" if trashed else None,
    )
    assert back_href(client.get("/email/message")) == ("/trash" if trashed else "/search")


@pytest.mark.parametrize(
    "destination",
    [
        "https://example.com/search?q=private",
        "//example.com/search",
        "javascript:alert(1)",
        "/settings",
        "/search/../settings",
        "/search\\example.com",
        "/search?q=value\nnext",
    ],
)
def test_unsafe_return_target_uses_local_fallback(reader, destination):
    client, _ = reader
    response = client.get(
        "/email/message",
        query_string={"return_to": destination},
        headers={"Referer": "http://localhost/search?q=ignored"},
    )
    assert back_href(response) == "/search"


@pytest.mark.parametrize(
    ("referer", "destination"),
    [
        ("http://localhost/search?q=annual&sort=date_desc&page=2", "/search?q=annual&sort=date_desc&page=2"),
        ("http://localhost/trash", "/trash"),
        ("https://example.com/search?q=foreign", "/search"),
        ("http://localhost/settings", "/search"),
    ],
)
def test_referer_fallback_only_accepts_local_result_lists(reader, referer, destination):
    client, _ = reader
    assert back_href(client.get("/email/message", headers={"Referer": referer})) == destination


def test_secondary_metadata_disclosure_keeps_headers_and_actions_accessible(reader):
    client, _ = reader
    document = html.fromstring(client.get("/email/message").data)
    details = document.get_element_by_id("ownmail-message-metadata")
    assert "hidden" in details.attrib
    toggle = document.get_element_by_id("ownmail-message-details-toggle")
    assert toggle.tag == "button"
    assert toggle.get("aria-expanded") == "false"
    assert toggle.get("aria-controls") == details.get("id")
    assert toggle.get("aria-label").startswith("Message details:")
    assert "2024" in toggle.text_content()
    for address in ["alex@example.com", "pat@example.com", "lee@example.com"]:
        assert address in details.text_content()
    assert "Project planning" in details.text_content()
    assert "The message body remains visible." in document.get_element_by_id("ownmail-email-content").text_content()
    back = document.get_element_by_id("ownmail-back-to-results")
    assert back.get("title") == "Back to results"
    assert back.text_content().strip() == "Back to results"
    menu = document.xpath('//details[@class="ownmail-email-menu"]')[0]
    assert menu.find("summary").get("aria-label") == "More message actions"
    assert [(link.get("href"), link.text_content().strip()) for link in menu.xpath(".//a")] == [
        ("/raw/message", "Original"),
        ("/download/message", "Download"),
    ]


@pytest.mark.parametrize("trashed", [False, True])
def test_toolbar_exposes_trash_or_restore_and_keeps_permanent_delete_in_more(reader, trashed):
    client, archive = reader
    archive.db.get_email_by_id.return_value = (
        "message",
        "message.eml",
        None,
        None,
        None,
        "2024-01-16" if trashed else None,
    )
    document = html.fromstring(client.get("/email/message").data)
    toolbar = document.xpath('//div[@class="ownmail-reader-actions"]')[0]
    buttons = toolbar.xpath("./button")
    assert len(buttons) == 1
    button = buttons[0]
    action, label = ("restoreEmail", "Restore from trash") if trashed else ("trashEmail", "Move to trash")
    assert button.get("onclick") == f"{action}('message')"
    assert button.get("aria-label") == button.get("title") == label
    assert "data-message-action" in button.attrib
    menu = toolbar.find("details")
    assert not menu.xpath(f".//button[@onclick=\"{action}('message')\"]")
    permanent_delete = menu.xpath(".//button[@onclick=\"deleteForever('message')\"]")
    assert bool(permanent_delete) is trashed


_POSITION_TEMPLATE = Path(__file__).parents[1] / "ownmail" / "templates" / "_result_state.html"
_POSITION_HARNESS = """
const assert = require('node:assert/strict');
const vm = require('node:vm');
const storage = new Map();
function page(path, reader = false, storageBlocked = false, readyState = 'interactive') {
    const handlers = {};
    const location = new URL(path, 'http://localhost');
    let focused = false;
    let scrolled = null;
    let scrollCalls = 0;
    let loadingCalls = 0;
    const row = {
        href: 'http://localhost/email/message?return_to=' + encodeURIComponent(path),
        focus(options) { focused = options.preventScroll; }
    };
    const list = {
        addEventListener(name, callback) { handlers['list:' + name] = callback; },
        querySelectorAll() { return [row]; }
    };
    const back = {
        href: 'http://localhost/search?q=annual&sort=date_asc&page=3',
        addEventListener(name, callback) { handlers['back:' + name] = callback; }
    };
    const context = {
        URL, location,
        showLoading() { loadingCalls++; },
        document: {
            readyState,
            addEventListener(name, callback) { handlers['document:' + name] = callback; },
            getElementById(id) {
                if (id === 'ownmail-email-list' && !reader) return list;
                if (id === 'ownmail-back-to-results' && reader) return back;
                return null;
            }
        },
        window: {
            scrollY: 648,
            addEventListener(name, callback) { handlers[name] = callback; },
            scrollTo(x, y) { scrollCalls++; scrolled = [x, y]; }
        },
        sessionStorage: {
            getItem(key) { if (storageBlocked) throw Error('blocked'); return storage.get(key) || null; },
            setItem(key, value) { if (storageBlocked) throw Error('blocked'); storage.set(key, value); },
            removeItem(key) { if (storageBlocked) throw Error('blocked'); storage.delete(key); }
        }
    };
    vm.runInNewContext(SOURCE, context);
    return {
        click(overrides = {}) {
            const event = {
                button: 0, detail: 1, defaultPrevented: false,
                preventDefault() { this.defaultPrevented = true; },
                target: {closest() { return row; }}, ...overrides
            };
            handlers[reader ? 'back:click' : 'list:click'](event);
            return event;
        },
        show() { handlers.pageshow(); },
        get focused() { return focused; },
        get scrolled() { return scrolled; },
        get scrollCalls() { return scrollCalls; },
        get loadingCalls() { return loadingCalls; }
    };
}
const listUrl = '/search?q=annual&sort=date_asc&page=3';
"""


def run_position_script(assertions):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not available")
    source = "const SOURCE = " + json.dumps(html.fragment_fromstring(_POSITION_TEMPLATE.read_text()).text) + ";\n"
    subprocess.run([node, "-e", source + _POSITION_HARNESS + assertions], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("ready_state", ["loading", "interactive"])
@pytest.mark.parametrize(("detail", "expected_focus"), [(0, True), (1, False)])
def test_explicit_back_restores_scroll_and_activation_focus_before_pageshow(ready_state, detail, expected_focus):
    run_position_script(
        """
page(listUrl).click();
const reader = page('/email/message', true);
const click = reader.click({detail: DETAIL});
assert.equal(reader.loadingCalls, 1);
assert.equal(reader.scrolled, null);
assert(!click.defaultPrevented);
const returned = page(listUrl, false, false, READY_STATE);
assert.deepEqual(returned.scrolled, [0, 648]);
assert.equal(returned.focused, EXPECTED_FOCUS);
assert.equal(storage.size, 0);
returned.show();
assert.equal(returned.scrollCalls, 1);
const fresh = page(listUrl);
fresh.show();
assert.equal(fresh.scrolled, null);
""".replace("READY_STATE", json.dumps(ready_state))
        .replace("DETAIL", json.dumps(detail))
        .replace("EXPECTED_FOCUS", json.dumps(expected_focus))
    )


def test_cached_list_restores_explicit_return_on_pageshow_once():
    run_position_script("""
const cached = page(listUrl);
cached.click();
page('/email/message', true).click({detail: 0});
assert.equal(cached.scrolled, null);
cached.show();
assert.deepEqual(cached.scrolled, [0, 648]);
assert.equal(cached.focused, true);
assert.equal(storage.size, 0);
cached.show();
assert.equal(cached.scrollCalls, 1);
""")


@pytest.mark.parametrize(
    "modifiers",
    [
        {"ctrlKey": True},
        {"metaKey": True},
        {"shiftKey": True},
        {"altKey": True},
        {"button": 1},
        {"defaultPrevented": True},
    ],
)
def test_modified_or_prevented_clicks_do_not_save_position_or_start_loading(modifiers):
    run_position_script(
        """
const modifiers = MODIFIERS;
page(listUrl).click(modifiers);
const reader = page('/email/message', true);
reader.click(modifiers);
assert.equal(storage.size, 0);
assert.equal(reader.loadingCalls, 0);
""".replace("MODIFIERS", json.dumps(modifiers))
    )


def test_result_position_does_not_change_other_queries_or_browser_back():
    run_position_script("""
page(listUrl).click();
page('/email/message', true).click();
const unrelated = page('/search?q=different');
unrelated.show();
assert.equal(unrelated.scrolled, null);
storage.clear();
page(listUrl).click();
const browserBack = page(listUrl);
browserBack.show();
assert.equal(browserBack.scrolled, null);
assert.equal(storage.size, 0);
""")


def test_unavailable_storage_does_not_interrupt_navigation():
    run_position_script("""
page(listUrl, false, true).click();
const reader = page('/email/message', true, true);
reader.click();
assert.equal(reader.loadingCalls, 1);
page(listUrl, false, true).show();
assert.equal(storage.size, 0);
""")


def test_returned_list_restores_while_parsing_without_external_resources(reader, shell_browser):
    client, archive = reader
    client.application.config["page_size"] = 2
    archive.search.return_value = [
        (identifier, "message.eml", "Annual review", "alex@example.com", "2024-01-15", "Message body")
        for identifier in ["other", "message", "next"]
    ]
    path = "/search?q=annual&sort=date_asc&page=3"
    page = client.get(path).data.decode()
    script = """
const assert = require('node:assert/strict');
const { JSDOM, ResourceLoader, VirtualConsole } = require('jsdom');
const scrolls = [];
const scriptErrors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', error => scriptErrors.push(error.message));
class UnavailableResources extends ResourceLoader {
    fetch() { return null; }
}
const dom = new JSDOM(PAGE, {
    url: 'http://localhost' + PATH,
    runScripts: 'dangerously',
    resources: new UnavailableResources(),
    virtualConsole,
    beforeParse(window) {
        window.matchMedia = () => ({ matches: false, addEventListener() {} });
        window.sessionStorage.setItem('ownmail-result-position', JSON.stringify({
            listUrl: PATH, messagePath: '/email/message', scrollY: 648, restore: true, restoreFocus: true
        }));
        window.scrollTo = (x, y) => {
            const document = window.document;
            scrolls.push({
                x, y,
                readyState: document.readyState,
                rows: document.querySelectorAll('.ownmail-email-row').length,
                footerPresent: !!document.querySelector('.ownmail-toolbar-bottom'),
                focusedPath: new URL(document.activeElement.href).pathname
            });
        };
    }
});
assert.deepEqual(scriptErrors, []);
assert.deepEqual(scrolls, [{
    x: 0, y: 648, readyState: 'loading', rows: 2,
    footerPresent: true, focusedPath: '/email/message'
}]);
assert.equal(dom.window.sessionStorage.getItem('ownmail-result-position'), null);
dom.window.dispatchEvent(new dom.window.Event('pageshow'));
assert.equal(scrolls.length, 1);
dom.window.close();
"""
    script = script.replace("PAGE", json.dumps(page)).replace("PATH", json.dumps(path))
    result = subprocess.run(["node", "-e", script], cwd=shell_browser, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def run_fit_browser(reader, browser_dir, auto_scale, width, assertions):
    client, archive = reader
    (archive.archive_dir / "message.eml").write_text(
        "From: sender@example.com\nSubject: Wide HTML\nContent-Type: text/html\n\n"
        '<div id="authored" style="width:1200px;font-size:20px">Readable at actual size.</div>'
    )
    client.application.config["auto_scale"] = auto_scale
    page = client.get("/email/message").data.decode()
    script = """
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
let contentWidth = WIDTH;
const dom = new JSDOM(PAGE, {
    url: 'http://localhost/email/message', runScripts: 'dangerously',
    beforeParse(window) {
        window.matchMedia = () => ({ matches: false, addEventListener() {} });
        Object.defineProperty(window.HTMLElement.prototype, 'clientWidth', {
            get() { return this.id === 'ownmail-email-content' ? contentWidth : 0; }
        });
        Object.defineProperty(window.HTMLElement.prototype, 'scrollWidth', {
            get() { return this.id === 'ownmail-email-content' ? 1200 : 0; }
        });
    }
});
const { window } = dom;
const { document } = window;
const content = document.getElementById('ownmail-email-content');
const button = document.getElementById('ownmail-fit-message');
const menu = document.querySelector('.ownmail-email-menu');
ASSERTIONS
dom.window.close();
"""
    script = script.replace("WIDTH", str(width)).replace("PAGE", json.dumps(page)).replace("ASSERTIONS", assertions)
    result = subprocess.run(["node", "-e", script], cwd=browser_dir, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("auto_scale", [True, False])
def test_wide_message_can_toggle_fit_without_changing_authored_styles(reader, shell_browser, auto_scale):
    run_fit_browser(
        reader,
        shell_browser,
        auto_scale,
        400,
        """
const initiallyFit = INITIAL_FIT;
assert(!button.hidden);
assert.equal(button.getAttribute('aria-controls'), content.id);
assert.equal(button.textContent, initiallyFit ? 'Show actual size' : 'Fit to width');
assert.equal(String(content.style.zoom), initiallyFit ? String(1 / 3) : '');
menu.open = true;
button.click();
assert.equal(button.textContent, initiallyFit ? 'Fit to width' : 'Show actual size');
assert.equal(String(content.style.zoom), initiallyFit ? '' : String(1 / 3));
assert.equal(content.style.overflow, initiallyFit ? 'auto' : 'hidden');
assert(!menu.open);
assert.equal(document.activeElement, menu.querySelector('summary'));
button.click();
assert.equal(String(content.style.zoom), initiallyFit ? String(1 / 3) : '');
assert.equal(document.getElementById('authored').getAttribute('style'), 'width:1200px;font-size:20px');
""".replace("INITIAL_FIT", json.dumps(auto_scale)),
    )
    assert reader[0].application.config["auto_scale"] is auto_scale


def test_fit_control_follows_overflow_when_viewport_changes(reader, shell_browser):
    run_fit_browser(
        reader,
        shell_browser,
        True,
        1200,
        """
assert(button.hidden);
assert.equal(content.style.zoom, '');
contentWidth = 390;
window.dispatchEvent(new window.Event('resize'));
assert(!button.hidden);
assert.equal(Number(content.style.zoom), 390 / 1200);
contentWidth = 1400;
window.dispatchEvent(new window.Event('resize'));
assert(button.hidden);
assert.equal(content.style.zoom, '');
assert.equal(content.style.overflow, 'auto');
""",
    )


def test_message_download_closes_menu_without_canceling_navigation(reader, shell_browser):
    run_fit_browser(
        reader,
        shell_browser,
        True,
        1200,
        """
const download = menu.querySelector('a[href="/download/message"]');
menu.open = true;
download.focus();
const click = new window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
assert(download.querySelector('span').dispatchEvent(click));
assert(!click.defaultPrevented);
assert(!menu.open);
assert.equal(document.activeElement, menu.querySelector('summary'));
""",
    )


def test_timestamp_toggles_metadata_without_moving_keyboard_focus(reader, shell_browser):
    run_fit_browser(
        reader,
        shell_browser,
        True,
        1200,
        """
const timestamp = document.getElementById('ownmail-message-details-toggle');
const metadata = document.getElementById(timestamp.getAttribute('aria-controls'));
assert.equal(timestamp.tagName, 'BUTTON');
assert(metadata.hidden);
timestamp.focus();
timestamp.click();
assert.equal(timestamp.getAttribute('aria-expanded'), 'true');
assert(!metadata.hidden);
assert.equal(document.activeElement, timestamp);
timestamp.click();
assert.equal(timestamp.getAttribute('aria-expanded'), 'false');
assert(metadata.hidden);
assert.equal(document.activeElement, timestamp);
""",
    )
