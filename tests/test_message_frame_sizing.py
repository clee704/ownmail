"""Message frame sizing in a real browser engine: no internal scroll, no clipping, reader viewport units."""

import json

import pytest

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
run_message_browser = test_email_contrast.run_contrast_browser
message_sanitizer = test_reader_spacing.spacing_sanitizer
# Any real font works; this one ships with the Playwright test dependency. U+EA60 is one of its glyphs.
ICON_FONT = next((test_email_contrast.SANITIZER_DIR / "node_modules" / "playwright-core").rglob("codicon*.ttf"), None)
LINE = "margin:0;font-size:13.3px;line-height:1.37"
LONG_URL = "https://example.com/" + "a" * 300
# Delays the response so the image arrives after the frame's load event.
LATE_IMAGE = """
        await page.route('https://fixture.test/late.svg', async route => {
            await new Promise(resolve => setTimeout(resolve, 1000));
            await route.fulfill({contentType: 'image/svg+xml',
                body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="900"></svg>'});
        });
        await message().locator('#late').evaluate(el => { el.src = 'https://fixture.test/late.svg'; });
        await page.waitForFunction(() => messageDocument().getElementById('late').naturalWidth === 300, null,
            {timeout: 5000});
        await settle();
        await check('after the late image');
"""
# Each case: body, CSS, element ids that must stay visible, steps after the first check, and
# CSS None for a message that goes through the sanitizer (needed for the viewport-unit rewrite).
CASES = {
    "fractional-line-height": (
        "".join(f'<p style="{LINE}">Line {i}</p>' for i in range(15)) + f'<p id="end" style="{LINE}">End</p>',
        "",
        ["end"],
        "",
    ),
    "fitted-wide-table": (
        '<table id="wide" width="1200" style="border-spacing:0"><tr><td style="height:333.3px">Wide</td></tr>'
        '</table><p id="end">End</p>',
        "",
        ["wide", "end"],
        "",
    ),
    "positioned-and-transformed": (
        '<p id="end">End of flow</p>'
        '<div id="moved" style="transform:translateY(300.7px)">Moved</div>'
        '<div id="abs" style="position:absolute;top:400.3px;left:0;width:50px;height:50px"></div>',
        "",
        ["end", "moved", "abs"],
        "",
    ),
    # The image overflows a fixed-height box, so only an observer on the image sees it load.
    "late-image": (
        '<p>Before</p><div style="height:20px"><img id="late" alt=""></div><p id="end">End</p>',
        "",
        ["late", "end"],
        LATE_IMAGE,
    ),
    # The rule matches only once the frame is taller than the first measurement.
    "media-query-after-sizing": (
        '<div style="height:400px">Tall</div><div id="grow"></div><p id="end">End</p>',
        "@media (min-height: 300px) { #grow { height: 100px } }",
        ["grow", "end"],
        "",
    ),
    "viewport-width-change": (
        "<p>" + "Reflowing synthetic text. " * 60 + '</p><p id="end">End</p>',
        "",
        ["end"],
        """
        for (const width of [700, 320]) {
            await page.setViewportSize({width, height: 740});
            await settle();
            await check('at width ' + width);
        }
        """,
    ),
    # A positioned box does not resize the container, so only the theme change re-runs sizing.
    "theme-change": (
        '<p id="end">End</p><div id="abs"></div>',
        "#abs { position: absolute; top: 0; left: 0; width: 10px; height: 10px }"
        " @media (prefers-color-scheme: dark) { #abs { height: 600.3px } }",
        ["end", "abs"],
        """
        await setTheme('dark');
        assert((await message().locator('#abs').boundingBox()).height > 600, 'The dark rule must apply');
        await check('after the theme change');
        """,
    ),
    # The swapped glyph is ten times larger; a positioned box does not resize the container. The glyph
    # takes the face only after the frame's load event, and the font response waits for the test, so the
    # font arrives after every other trigger has run.
    "font-swap": (
        '<p id="end">End</p>'
        '<div id="icon" style="position:absolute;top:150px;left:0;line-height:normal">&#xea60;</div>',
        "@font-face { font-family: Swap; src: url(https://fixture.test/swap.ttf); size-adjust: 1000% }",
        ["end", "icon"],
        """
        let release;
        const held = new Promise(resolve => { release = resolve; });
        await page.route('https://fixture.test/swap.ttf', async route => {
            await held;
            await route.fulfill({contentType: 'font/ttf', body: fs.readFileSync(FONT)});
        });
        const requested = page.waitForRequest('https://fixture.test/swap.ttf');
        await message().locator('#icon').evaluate(el => { el.style.fontFamily = 'Swap'; });
        await requested;
        await settle();
        assert((await message().locator('#icon').boundingBox()).height < 100, 'The font must not have swapped yet');
        await check('while the font loads');
        release();
        await page.waitForFunction(() => [...messageDocument().fonts].every(face => face.status === 'loaded') &&
            messageDocument().getElementById('icon').getBoundingClientRect().height > 100, null, {timeout: 5000});
        await settle();
        await check('after the font swap');
        """,
    ),
    "long-urls": (
        f'<p id="url">{LONG_URL}</p><table><tr><td id="cell">{LONG_URL}</td></tr></table><p id="end">End</p>',
        "",
        ["url", "cell", "end"],
        "",
    ),
    "viewport-units": (
        '<div id="tall" style="min-height:100vh">Viewport height</div><p id="end">End</p>',
        None,
        ["tall", "end"],
        "",
    ),
}


@pytest.mark.parametrize("backstop", [False, True], ids=["no-scroll", "no-clip"])
@pytest.mark.parametrize("case", CASES)
def test_message_frame_never_scrolls_or_clips(shell_app, browser_node, message_sanitizer, case, backstop):
    """Backstop off: the frame has no scrollable overflow. Backstop on: listed elements lie in its box."""
    app, _ = shell_app
    body, css, ids, steps = CASES[case]
    if css is None:
        body = message_sanitizer.sanitize(body)[0]
    elif case == "font-swap":
        assert ICON_FONT, "The font swap case needs a font from the Playwright package"
        steps = steps.replace("FONT", json.dumps(str(ICON_FONT)))
    run_message_browser(
        app,
        browser_node,
        body,
        css or "",
        """
        const check = async label => {
            const result = await page.evaluate(([ids, backstop]) => {
                const doc = messageDocument(), scroller = doc.scrollingElement;
                if (!backstop) {
                    scroller.scrollTop = 1e6;
                    scroller.scrollLeft = 1e6;
                    return {top: scroller.scrollTop, left: scroller.scrollLeft,
                        height: [scroller.scrollHeight, scroller.clientHeight],
                        width: [scroller.scrollWidth, scroller.clientWidth]};
                }
                return ids.map(id => {
                    const rect = doc.getElementById(id).getBoundingClientRect();
                    return [id, rect.left, rect.top, rect.right, rect.bottom, scroller.clientWidth, scroller.clientHeight];
                }).filter(([, left, top, right, bottom, width, height]) =>
                    left < 0 || top < 0 || right > width || bottom > height);
            }, [IDS, BACKSTOP]);
            const detail = label + ': ' + JSON.stringify(result);
            if (BACKSTOP) {
                assert.deepEqual(result, [], detail);
            } else {
                assert(result.top === 0 && result.left === 0, detail);
                assert(result.height[0] <= result.height[1] && result.width[0] <= result.width[1], detail);
            }
        };
        await check('first layout');
        STEPS
        """.replace("IDS", repr(ids))
        .replace("BACKSTOP", "true" if backstop else "false")
        .replace("STEPS", steps),
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
        backstop=backstop,
    )


def test_message_viewport_units_resolve_against_reader_viewport(shell_app, browser_node, message_sanitizer):
    app, _ = shell_app
    run_message_browser(
        app,
        browser_node,
        message_sanitizer.sanitize('<div id="half" style="height:50vh;width:50vw"></div><p>End</p>')[0],
        "",
        """
        for (const size of [null, {width: 430, height: 900}, {width: 390, height: 600}]) {
            if (size) {
                await page.setViewportSize(size);
                await settle();
            }
            const [box, width, height] = await page.evaluate(() => [
                messageDocument().getElementById('half').getBoundingClientRect().toJSON(), innerWidth, innerHeight]);
            const detail = JSON.stringify([box, width, height]);
            assert(Math.abs(box.width - width / 2) <= 0.5, detail);
            assert(Math.abs(box.height - height / 2) <= 0.5, detail);
        }
        """,
        theme="light",
        auto_scale=True,
        viewport=(390, 740),
    )
