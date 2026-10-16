"""Reader scrolling and authored layout checks in a real browser engine."""

import pytest

from tests import test_email_contrast

shell_app = test_email_contrast.shell_app
run_message_browser = test_email_contrast.run_contrast_browser
TINY_FOOTER = """
<div style="height:1px;font-size:13px;line-height:1"><img width="1" height="1"
    src="https://fixture.test/pixel.svg" alt=""></div>
"""


def test_tiny_message_overflow_does_not_capture_vertical_scrolling(shell_app, browser_node):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        '<table style="width:100%;height:1600px"><tr><td>Long synthetic message</td></tr></table>' + TINY_FOOTER,
        "",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0,
            'The message must not independently scroll its tiny vertical overflow');
        assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        assert.equal(await page.locator('#ownmail-fit-message').evaluate(el => el.hidden), true);
        const box = await content.boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + 100);
        for (let i = 0; i < 3; i++) {
            const previous = await page.evaluate(() => window.scrollY);
            await page.mouse.wheel(0, 180);
            await page.waitForFunction(y => window.scrollY > y + 100, previous);
            assert.equal(await viewport.evaluate(el => el.scrollTop), 0);
        }
        // A plain click moves focus into the frame; the wheel must still scroll the page.
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.mouse.click(box.x + box.width / 2, 100);
        await settle();
        await page.mouse.wheel(0, 180);
        await page.waitForFunction(() => window.scrollY > 100);
        assert.equal(await page.evaluate(() => messageDocument().scrollingElement.scrollTop), 0);
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
    )


LONG_MESSAGE = "".join(
    f'<p id="p{i}" style="margin:0;padding:8px 0;line-height:24px">Synthetic paragraph {i} with enough words to select.</p>'
    + ('<p><a id="link" href="https://x.invalid/link" target="_blank">First link</a></p>' if i == 3 else "")
    for i in range(150)
)


def test_keys_scroll_the_page_after_clicking_in_the_message(shell_app, browser_node):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        LONG_MESSAGE,
        "",
        """
        const engine = process.env.OWNMAIL_BROWSER_ENGINE || 'chromium';
        // Playwright's Chromium mouse helpers hang while a button is held over a
        // script-less frame, so Chromium input goes through CDP.
        const cdp = engine === 'chromium' ? await page.context().newCDPSession(page) : null;
        const mouse = async (type, x, y, buttons) => {
            if (!cdp) {
                await page.mouse.move(x, y);
                if (type === 'down') await page.mouse.down();
                if (type === 'up') await page.mouse.up();
                return;
            }
            await cdp.send('Input.dispatchMouseEvent', {
                type: {move: 'mouseMoved', down: 'mousePressed', up: 'mouseReleased'}[type], x, y,
                button: type === 'move' && !buttons ? 'none' : 'left',
                buttons: buttons ?? (type === 'down' ? 1 : 0), clickCount: 1});
        };
        // Viewport coordinates of a frame element (frame locator boxes hang in Chromium).
        const rect = selector => page.evaluate(selector => {
            const frame = document.getElementById('ownmail-email-frame');
            const box = frame.contentDocument.querySelector(selector).getBoundingClientRect();
            const origin = frame.getBoundingClientRect();
            return {x: origin.x + box.x, y: origin.y + box.y, width: box.width, height: box.height};
        }, selector);
        const click = async selector => {
            const box = await rect(selector);
            await mouse('move', box.x + 30, box.y + 10);
            await mouse('down', box.x + 30, box.y + 10);
            await mouse('up', box.x + 30, box.y + 10);
            await settle();
        };
        const state = () => page.evaluate(() => ({
            y: window.scrollY,
            frameScroll: messageDocument().scrollingElement.scrollTop,
            selection: messageDocument().getSelection().toString(),
            active: document.activeElement.id,
        }));
        // Keyboard scrolling is animated; wait until the position holds still.
        const stable = async () => {
            let y = await page.evaluate(() => window.scrollY);
            for (let i = 0; i < 40; i++) {
                await page.waitForTimeout(80);
                const next = await page.evaluate(() => window.scrollY);
                if (next === y) return;
                y = next;
            }
        };
        const scrollTo = async y => {
            await page.evaluate(y => window.scrollTo(0, y), y);
            await stable();
            assert.equal(await page.evaluate(() => window.scrollY), y);
        };
        const scrolls = async (key, direction) => {
            const before = await state();
            await page.keyboard.press(key);
            await stable();
            const after = await state();
            assert.ok((after.y - before.y) * direction >= 20, `${key}: ${before.y} to ${after.y}`);
            assert.equal(after.frameScroll, 0, key);
        };
        const keys = async () => {
            await scrollTo(0);
            await scrolls('Space', 1);
            await scrolls('Space', 1);
            await scrolls('Shift+Space', -1);
            await scrolls('PageDown', 1);
            await scrolls('ArrowDown', 1);
        };

        await page.mouse.move(400, 400);
        await keys();
        await scrollTo(0);
        await click('#p5');
        assert.equal((await state()).active, 'ownmail-email-viewport');
        await keys();

        // A click deep in the message leaves the page where it is.
        await scrollTo(2000);
        const deep = await page.evaluate(() => {
            const frame = document.getElementById('ownmail-email-frame');
            const top = -frame.getBoundingClientRect().y + 200;
            return '#' + [...frame.contentDocument.querySelectorAll('p[id]')].find(p => p.offsetTop > top).id;
        });
        await click(deep);
        assert.equal((await state()).y, 2000);
        await scrolls('Space', 1);

        // Click-drag selects text; focus stays in the frame so native copy works.
        await scrollTo(0);
        const start = await rect('#p6');
        await mouse('move', start.x + 5, start.y + 10);
        await mouse('down', start.x + 5, start.y + 10);
        for (let i = 1; i <= 5; i++) await mouse('move', start.x + 5 + 40 * i, start.y + 10 + 12 * i, 1);
        await mouse('up', start.x + 205, start.y + 70);
        await settle();
        await page.waitForTimeout(300);
        const selected = await state();
        assert.ok(selected.selection.includes('paragraph 6 with'), selected.selection);
        assert.equal(selected.active, 'ownmail-email-frame');
        await page.keyboard.press('ControlOrMeta+c');
        if (engine === 'chromium') {
            // The reader origin is not a secure context, so read the clipboard from one that is.
            const reader = await browser.newContext();
            await reader.grantPermissions(['clipboard-read'], {origin: 'https://clipboard.test'});
            const clipboardPage = await reader.newPage();
            await clipboardPage.route('**/*', route => route.fulfill({contentType: 'text/html', body: '<p>clipboard</p>'}));
            await clipboardPage.goto('https://clipboard.test/');
            assert.equal(await clipboardPage.evaluate(() => navigator.clipboard.readText()), selected.selection);
            await reader.close();
        }
        await page.evaluate(() => {
            const field = document.createElement('textarea');
            field.id = 'paste-target';
            document.body.prepend(field);
            field.focus({preventScroll: true});
        });
        await page.keyboard.press('ControlOrMeta+v');
        assert.equal(await page.locator('#paste-target').inputValue(), selected.selection);
        await page.locator('#paste-target').evaluate(el => el.remove());

        // A plain click that collapses the selection returns focus within a fraction of a second.
        await scrollTo(0);
        await click('#p6');
        await page.waitForTimeout(250);
        assert.equal((await state()).active, 'ownmail-email-viewport');
        await scrolls('Space', 1);

        // Tab reaches a message link (WebKit on macOS skips links on plain Tab), and Enter opens it.
        await page.context().route('https://x.invalid/**', route => route.abort().catch(() => {}));
        await scrollTo(0);
        await click('#p1');
        await page.keyboard.press(engine === 'webkit' ? 'Alt+Tab' : 'Tab');
        await settle();
        assert.equal(await page.evaluate(() => messageDocument().activeElement.id), 'link');
        assert.equal((await state()).active, 'ownmail-email-frame');
        const popup = page.context().waitForEvent('page', {timeout: 2000});
        const opened = page.context().waitForEvent('request',
            {predicate: request => request.url() === 'https://x.invalid/link', timeout: 2000});
        await page.keyboard.press('Enter');
        await Promise.all([popup, opened]);
        """,
        theme="light",
        viewport=(800, 600),
    )


@pytest.mark.parametrize(
    "body",
    [
        '<table id="wide" width="1200" height="1500" style="border-spacing:0"><tr>'
        '<td style="width:600px">Left edge</td><td style="width:600px;text-align:right">Right edge</td>'
        "</tr></table>",
        '<img id="wide" width="1200" height="1500" src="https://fixture.test/wide.svg" alt="Wide message">',
    ],
    ids=["table", "image"],
)
def test_wide_messages_fit_and_scroll_at_actual_size(shell_app, browser_node, body):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        body + TINY_FOOTER,
        "",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const button = page.locator('#ownmail-fit-message');
        const wide = message().locator('#wide');
        const authoredStyle = await wide.getAttribute('style');
        assert.equal(await button.getAttribute('aria-controls'), await page.locator('#ownmail-email-frame').getAttribute('id'));
        const toggle = async () => {
            await page.locator('.ownmail-email-menu > summary').click();
            await button.click();
            await settle();
            assert.equal(await page.locator('.ownmail-email-menu').evaluate(el => el.open), false);
        };
        const checkFitted = async () => {
            assert.equal(await button.textContent(), 'Show actual size');
            assert.equal(await button.evaluate(el => el.hidden), false);
            assert.equal(await wide.evaluate(el => el.offsetWidth), 1200);
            assert.equal(await wide.getAttribute('style'), authoredStyle);
            const rootBox = await viewport.boundingBox();
            const wideBox = await wide.boundingBox();
            assert(wideBox.width < 1200);
            assert(Math.abs(wideBox.height - 1500 * wideBox.width / 1200) <= 1);
            assert(wideBox.x + wideBox.width <= rootBox.x + rootBox.width + 1);
            assert.equal(await viewport.evaluate(el => {el.scrollLeft = 100; return el.scrollLeft;}), 0);
            assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
            assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        };
        await checkFitted();
        const phoneWidth = (await wide.boundingBox()).width;
        await page.setViewportSize({width:700, height:740});
        await settle();
        await checkFitted();
        assert((await wide.boundingBox()).width > phoneWidth + 200);
        await page.setViewportSize({width:390, height:740});
        await settle();
        for (let i = 0; i < 2; i++) {
            await toggle();
            assert.equal(await button.textContent(), 'Fit to width');
            assert.equal((await wide.boundingBox()).width, 1200);
            assert.equal((await wide.boundingBox()).height, 1500);
            assert.equal(await wide.getAttribute('style'), authoredStyle);
            const maximum = await viewport.evaluate(el => el.scrollWidth - el.clientWidth);
            assert(maximum > 800);
            assert.deepEqual(await page.evaluate(() => {
                const scroller = messageDocument().scrollingElement;
                scroller.scrollLeft = 1e6;
                scroller.scrollTop = 1e6;
                return [scroller.scrollLeft, scroller.scrollTop];
            }), [0, 0], 'At actual size the reader viewport scrolls, the frame does not');
            const rootBox = await viewport.boundingBox();
            await page.mouse.move(rootBox.x + rootBox.width / 2, rootBox.y + 100);
            await page.mouse.wheel(1800, 0);
            await page.waitForFunction(() => {
                const el = document.getElementById('ownmail-email-viewport') ||
                    document.getElementById('ownmail-email-content');
                return el.scrollLeft >= el.scrollWidth - el.clientWidth - 1;
            });
            assert((await wide.boundingBox()).x + 1200 <= rootBox.x + rootBox.width + 1);
            const horizontal = await viewport.evaluate(el => el.scrollLeft);
            await message().locator('img').last().evaluate(el => {
                el.src = 'data:image/svg+xml,' + encodeURIComponent(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>');
            });
            await page.waitForFunction(() => [...messageDocument().querySelectorAll('#ownmail-email-content img')]
                .every(el => el.complete));
            await settle();
            assert.equal(await viewport.evaluate(el => el.scrollLeft), horizontal,
                'Image loading must retain horizontal reading position');
            await page.setViewportSize({width:391, height:740});
            await page.setViewportSize({width:390, height:740});
            await settle();
            assert(Math.abs(await viewport.evaluate(el => el.scrollLeft) - horizontal) <= 1,
                'Resizing must retain horizontal reading position');
            const previous = await page.evaluate(() => window.scrollY);
            await page.mouse.wheel(0, 180);
            await page.waitForFunction(y => window.scrollY > y + 100, previous);
            assert.equal(await viewport.evaluate(el => el.scrollTop), 0);
            assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
            await toggle();
            await checkFitted();
        }
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
    )


@pytest.mark.parametrize("sender_sizing", ["", "box-sizing:border-box;"])
def test_message_image_box_sizing_matches_standalone_html(shell_app, browser_node, sender_sizing):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        f'<img id="padded-logo" alt="" style="width:120px;height:40px;padding-right:24px;{sender_sizing}">',
        "",
        """
        const sizing = await message().locator('#padded-logo').evaluate(el => ({
            boxSizing: getComputedStyle(el).boxSizing, width: el.getBoundingClientRect().width
        }));
        assert.deepEqual(sizing, SIZING);
        assert.equal(await message().locator('#ownmail-email-content').evaluate(el => getComputedStyle(el).boxSizing), 'border-box');
        assert.equal(await page.locator('.ownmail-app-shell').evaluate(el => getComputedStyle(el).boxSizing), 'border-box');
        """.replace(
            "SIZING",
            '{boxSizing: "border-box", width: 120}' if sender_sizing else '{boxSizing: "content-box", width: 144}',
        ),
        theme="light",
        auto_scale=True,
    )


def test_late_image_load_and_resize_recalculate_fit(shell_app, browser_node):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        '<p>Message with a delayed image</p><img id="late" alt="">',
        "",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const button = page.locator('#ownmail-fit-message');
        assert.equal(await button.evaluate(el => el.hidden), true);
        await message().locator('#late').evaluate(el => {
            el.src = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="1200"></svg>');
        });
        await page.waitForFunction(() => messageDocument().getElementById('late').naturalWidth === 640);
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), false);
        assert(Math.abs((await message().locator('#late').boundingBox()).width -
            (await viewport.boundingBox()).width) <= 1);
        assert.equal(await viewport.evaluate(el => {el.scrollLeft = 100; return el.scrollLeft;}), 0);
        await page.setViewportSize({width:1000, height:740});
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), true);
        assert.equal((await message().locator('#late').boundingBox()).width, 640);
        await page.setViewportSize({width:430, height:740});
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), false);
        assert(Math.abs((await message().locator('#late').boundingBox()).width -
            (await viewport.boundingBox()).width) <= 1);
        assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
        is_mobile=True,
    )


@pytest.mark.parametrize("constraint", ["height:240px", "max-height:240px"])
def test_constrained_message_preserves_content_and_attachment_position(shell_app, browser_node, constraint):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        """
        <p id="start" style="margin:32px 0 24px;height:36px">Message start</p>
        <div id="float" style="float:left;width:180px;height:900px;position:relative">
            <span id="end" style="position:absolute;bottom:0">Message end</span>
        </div>
        """,
        f"#ownmail-email-content {{{constraint}}}",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const box = await content.boundingBox();
        const outer = await viewport.boundingBox();
        const start = await message().locator('#start').boundingBox();
        const floated = await message().locator('#float').boundingBox();
        const end = await message().locator('#end').boundingBox();
        const attachments = await page.locator('.ownmail-attachments').boundingBox();
        assert.equal(start.y - box.y, 32, 'The first sender margin remains inside the message');
        assert.equal(floated.y - start.y - start.height, 24);
        assert.equal(floated.height, 900);
        assert(outer.y + outer.height >= end.y + end.height - 1, 'The message end must not be clipped');
        assert(attachments.y >= end.y + end.height, 'Attachments must follow all message content');
        assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        await message().locator('#end').scrollIntoViewIfNeeded();
        assert(await message().locator('#end').evaluate(el => {
            const rect = el.getBoundingClientRect();
            return el.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
        }), 'The end of the authored content is visible');
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
        is_mobile=True,
        attachments=[{"filename": "synthetic.txt", "url_name": "synthetic.txt", "kind": "Text", "size": "1 KB"}],
    )


@pytest.mark.parametrize("auto_scale", [True, False], ids=["fitted", "actual-size"])
def test_percentage_height_content_does_not_grow_when_exposing_footer(shell_app, browser_node, auto_scale):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        """
        <div id="percentage" style="height:100%;width:1200px">Authored percentage height</div>
        <div id="footer" style="height:25px;width:1200px;line-height:25px">Complete message footer</div>
        """,
        "#ownmail-email-content {height:240px}",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const child = message().locator('#percentage');
        const checkLayout = async () => {
            const childBox = await child.boundingBox();
            const footer = await message().locator('#footer').boundingBox();
            const outer = await viewport.boundingBox();
            const attachments = await page.locator('.ownmail-attachments').boundingBox();
            const scale = childBox.width / 1200;
            assert(Math.abs(childBox.height / scale - 240) <= 1,
                'Making the footer readable must not enlarge percentage-height content');
            assert(Math.abs(footer.height / scale - 25) <= 1);
            assert(Math.abs(footer.y - childBox.y - childBox.height) <= 1);
            assert(outer.y + outer.height >= footer.y + footer.height - 1,
                'The viewport must contain the complete overflowing footer');
            assert(attachments.y >= footer.y + footer.height - 1);
            assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
            assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        };
        await checkLayout();
        for (const width of [430, 390, 430]) {
            await page.setViewportSize({width, height:740});
            await settle();
            await checkLayout();
        }
        await page.locator('.ownmail-email-menu > summary').click();
        await page.locator('#ownmail-fit-message').click();
        await settle();
        await checkLayout();
        """,
        theme="light",
        auto_scale=auto_scale,
        viewport=(390, 740),
        is_mobile=True,
        attachments=[{"filename": "synthetic.txt", "url_name": "synthetic.txt", "kind": "Text", "size": "1 KB"}],
    )


def test_sender_flex_layout_survives_fitting_and_actual_size(shell_app, browser_node):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        '<div id="left" style="width:600px;flex:none">Left</div>'
        '<div id="right" style="width:600px;flex:none">Right</div>',
        "#ownmail-email-content {display:flex}",
        """
        const content = message().locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const checkLayout = async fitted => {
            assert.equal(await content.evaluate(el => getComputedStyle(el).display), 'flex');
            assert.equal(await content.locator('style').textContent(), '#ownmail-email-content {display:flex}');
            for (const id of ['left', 'right']) {
                assert.equal(await message().locator('#' + id).getAttribute('style'), 'width:600px;flex:none');
            }
            const left = await message().locator('#left').boundingBox();
            const right = await message().locator('#right').boundingBox();
            const outer = await viewport.boundingBox();
            assert.equal(left.y, right.y, 'The sender columns must stay side by side');
            assert(Math.abs(right.x - left.x - left.width) <= 1);
            assert.equal(left.width, right.width);
            if (fitted) {
                assert(left.width < 600);
                assert(right.x + right.width <= outer.x + outer.width + 1);
            } else {
                assert.equal(left.width, 600);
                assert(await viewport.evaluate(el => {
                    el.scrollLeft = el.scrollWidth;
                    return el.scrollLeft > 800;
                }));
                const reached = await message().locator('#right').boundingBox();
                assert(Math.abs(reached.x + reached.width - outer.x - outer.width) <= 1,
                    'The right column edge must remain reachable at actual size');
            }
        };
        await checkLayout(true);
        for (const fitted of [false, true]) {
            await page.locator('.ownmail-email-menu > summary').click();
            await page.locator('#ownmail-fit-message').click();
            await settle();
            await checkLayout(fitted);
        }
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
        is_mobile=True,
    )


def test_reader_reload_restores_session_position_after_fitting(shell_app, browser_node):
    """A real layout verifies restoration; this is not a physical iPhone check."""
    app, archive = shell_app
    (archive.archive_dir / "message.eml").write_text(
        "From: sender@example.com\nSubject: Long reader\nContent-Type: text/html\n\n"
        '<div style="height:3600px">A long synthetic message.</div>'
    )
    archive.db.get_email_by_id.return_value = ("message", "message.eml", None, None, None, None)
    response = app.test_client().get("/email/message")
    assert response.status_code == 200
    run_message_browser(
        app,
        browser_node,
        "",
        "",
        """
        assert.equal(await page.locator('head meta[name="theme-color"]').getAttribute('content'), '#ffffff');
        await setTheme('dark');
        assert.equal(await page.locator('head meta[name="theme-color"]').getAttribute('content'), '#202124');
        // Init scripts also run in the message frame's initial document.
        await page.addInitScript(() => { if (window === window.top) history.scrollRestoration = 'manual'; });
        await page.evaluate(() => {
            history.scrollRestoration = 'manual';
            window.scrollTo(0, 870);
            window.dispatchEvent(new PageTransitionEvent('pagehide'));
        });
        const saved = await page.evaluate(() => JSON.parse(sessionStorage.getItem('ownmail-reading-position')));
        assert.equal(saved.scrollY, 870);
        assert.deepEqual(Object.keys(saved).sort(), ['scrollY', 'url', 'version']);
        await page.reload({waitUntil:'load'});
        await settle();
        assert.equal(await page.evaluate(() => window.scrollY), 870);
        // A replaced file must not inherit the old file's checkpoint.
        await page.route('http://ownmail.test/email/synthetic', route => route.fulfill({
            contentType:'text/html', headers:input.pageHeaders,
            body:input.page.replace(/data-reader-version="[^"]*"/, 'data-reader-version="changed"')
        }));
        await page.reload({waitUntil:'load'});
        await settle();
        assert.equal(await page.evaluate(() => window.scrollY), 0);
        // Retry must make a new GET even when the current address has a fragment.
        await page.evaluate(() => {
            location.hash = 'resume';
            ownmailConnectionError('Could not confirm the action. Reload to check the current state.');
        });
        const reloaded = page.waitForEvent('load');
        await page.locator('#ownmail-action-retry').click();
        await reloaded;
        await settle();
        assert(await page.locator('#ownmail-action-feedback').evaluate(el => el.hidden));
        """,
        theme="light",
        viewport=(390, 740),
        is_mobile=True,
        auto_scale=True,
        rendered_page=response.data.decode(),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )
