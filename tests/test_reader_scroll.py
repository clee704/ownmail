"""Reader scrolling and authored layout checks in a real browser engine."""

import pytest

from tests import test_email_contrast

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser
run_message_browser = test_email_contrast.run_contrast_browser
TINY_FOOTER = """
<div style="height:1px;font-size:13px;line-height:1"><img width="1" height="1"
    src="https://fixture.test/pixel.svg" alt=""></div>
"""


def test_tiny_message_overflow_does_not_capture_vertical_scrolling(shell_app, contrast_browser):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        '<table style="width:100%;height:1600px"><tr><td>Long synthetic message</td></tr></table>' + TINY_FOOTER,
        "",
        """
        const content = page.locator('#ownmail-email-content');
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
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
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
def test_wide_messages_fit_and_scroll_at_actual_size(shell_app, contrast_browser, body):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        body + TINY_FOOTER,
        "",
        """
        const content = page.locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const button = page.locator('#ownmail-fit-message');
        const wide = page.locator('#wide');
        const authoredStyle = await wide.getAttribute('style');
        const toggle = async () => {
            await page.locator('.ownmail-email-menu > summary').click();
            await button.click();
            await settle();
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
            await page.locator('img').last().evaluate(el => {
                el.src = 'data:image/svg+xml,' + encodeURIComponent(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>');
            });
            await page.waitForFunction(() => [...document.querySelectorAll('#ownmail-email-content img')]
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


def test_late_image_load_and_resize_recalculate_fit(shell_app, contrast_browser):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        '<p>Message with a delayed image</p><img id="late" alt="">',
        "",
        """
        const content = page.locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const button = page.locator('#ownmail-fit-message');
        assert.equal(await button.evaluate(el => el.hidden), true);
        await page.locator('#late').evaluate(el => {
            el.src = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="1200"></svg>');
        });
        await page.waitForFunction(() => document.getElementById('late').naturalWidth === 640);
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), false);
        assert((await page.locator('#late').boundingBox()).width < 400);
        assert.equal(await viewport.evaluate(el => {el.scrollLeft = 100; return el.scrollLeft;}), 0);
        await page.setViewportSize({width:1000, height:740});
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), true);
        assert.equal((await page.locator('#late').boundingBox()).width, 640);
        await page.setViewportSize({width:430, height:740});
        await settle();
        assert.equal(await button.evaluate(el => el.hidden), false);
        assert((await page.locator('#late').boundingBox()).width < 430);
        assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
        is_mobile=True,
    )


@pytest.mark.parametrize("constraint", ["height:240px", "max-height:240px"])
def test_constrained_message_preserves_content_and_attachment_position(shell_app, contrast_browser, constraint):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        """
        <p id="start" style="margin:32px 0 24px;height:36px">Message start</p>
        <div id="float" style="float:left;width:180px;height:900px;position:relative">
            <span id="end" style="position:absolute;bottom:0">Message end</span>
        </div>
        """,
        f"#ownmail-email-content {{{constraint}}}",
        """
        const content = page.locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const box = await content.boundingBox();
        const outer = await viewport.boundingBox();
        const start = await page.locator('#start').boundingBox();
        const floated = await page.locator('#float').boundingBox();
        const end = await page.locator('#end').boundingBox();
        const attachments = await page.locator('.ownmail-attachments').boundingBox();
        assert.equal(start.y - box.y, 32, 'The first sender margin remains inside the message');
        assert.equal(floated.y - start.y - start.height, 24);
        assert.equal(floated.height, 900);
        assert(outer.y + outer.height >= end.y + end.height - 1, 'The message end must not be clipped');
        assert(attachments.y >= end.y + end.height, 'Attachments must follow all message content');
        assert.equal(await content.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        assert.equal(await viewport.evaluate(el => {el.scrollTop = 100; return el.scrollTop;}), 0);
        await page.locator('#end').scrollIntoViewIfNeeded();
        assert(await page.locator('#end').evaluate(el => {
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
def test_percentage_height_content_does_not_grow_when_exposing_footer(shell_app, contrast_browser, auto_scale):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        """
        <div id="percentage" style="height:100%;width:1200px">Authored percentage height</div>
        <div id="footer" style="height:25px;width:1200px;line-height:25px">Complete message footer</div>
        """,
        "#ownmail-email-content {height:240px}",
        """
        const content = page.locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const child = page.locator('#percentage');
        const checkLayout = async () => {
            const childBox = await child.boundingBox();
            const footer = await page.locator('#footer').boundingBox();
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


def test_sender_flex_layout_survives_fitting_and_actual_size(shell_app, contrast_browser):
    app, _ = shell_app
    run_message_browser(
        app,
        contrast_browser,
        '<div id="left" style="width:600px;flex:none">Left</div>'
        '<div id="right" style="width:600px;flex:none">Right</div>',
        "#ownmail-email-content {display:flex}",
        """
        const content = page.locator('#ownmail-email-content');
        const viewport = page.locator('#ownmail-email-viewport, #ownmail-email-content').first();
        const checkLayout = async fitted => {
            assert.equal(await content.evaluate(el => getComputedStyle(el).display), 'flex');
            assert.equal(await content.locator('style').textContent(), '#ownmail-email-content {display:flex}');
            for (const id of ['left', 'right']) {
                assert.equal(await page.locator('#' + id).getAttribute('style'), 'width:600px;flex:none');
            }
            const left = await page.locator('#left').boundingBox();
            const right = await page.locator('#right').boundingBox();
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
                const reached = await page.locator('#right').boundingBox();
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
