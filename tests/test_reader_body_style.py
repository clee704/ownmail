"""Sender body styling at the reader boundary."""

import json
from email.message import EmailMessage

import pytest

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


@pytest.mark.parametrize("style_location", ["head", "body"])
def test_malformed_body_qualifiers_do_not_activate_rules(
    shell_app, contrast_browser, spacing_sanitizer, style_location
):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=False)
    css = """
        body .probe {width:17px;}
        body.123 .probe {width:101px;}
        body#123 .probe {width:102px;}
        body.- .probe {width:103px;}
        body[data-number=123] .probe {width:104px;}
        body[data-hyphen=-] .probe {width:105px;}
        body[data-negative=-1] .probe {width:106px;}
        body[data-number="123"] .quoted {border-top:3px solid black;}
        body[data-valid=--1] .valid {border-top:5px solid black;}
    """
    style = f"<style>{css}</style>"
    source = (
        f"<html><head>{style if style_location == 'head' else ''}</head>"
        '<body class="123 -" id="123" data-number="123" data-hyphen="-" data-negative="-1" data-valid="--1">'
        f"{style if style_location == 'body' else ''}"
        '<div class="probe quoted valid">Synthetic</div></body></html>'
    )
    message = EmailMessage()
    message["Subject"] = "Synthetic malformed body selectors"
    message["From"] = "sender@example.com"
    message.set_content(source, subtype="html")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        r"""
        const reference = await browser.newPage();
        try {
            await reference.setContent(__SOURCE__);
            const read = el => ({width:getComputedStyle(el).width, border:getComputedStyle(el).borderTopWidth});
            const expected = await reference.locator('.probe').evaluate(read);
            assert.deepEqual(expected, {width:'17px', border:'5px'});
            assert.deepEqual(await page.locator('#ownmail-email-content .probe').evaluate(read), expected,
                'Invalid source selectors must remain invalid instead of activating a rule');
        } finally {
            await reference.close();
        }
        """.replace("__SOURCE__", json.dumps(source)),
        theme="light",
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


@pytest.mark.parametrize("style_location", ["head", "body"])
def test_qualified_body_rules_keep_matching_cascade_and_message_scope(
    shell_app, contrast_browser, spacing_sanitizer, style_location
):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=False)
    css = """
        /* Sender markup-like comment <p> must remain safe (TASK-119). */
        body .probe {width:9px;}
        body.main .class-probe {width:21px;}
        body[class~="main"] .attribute-probe {width:31px;}
        body[class = "main compact"] .exact-probe {width:41px;}
        BODY#message .id-probe {width:51px;}
        body.main#message[class~="compact"]>.child-probe {width:61px;}
        body[data-layout="wide"] .data-probe {width:71px;}
        body#message .cascade-probe {width:81px;}
        body.main.main .cascade-probe {width:91px;}
        body.other .nonmatch-probe {width:101px;}
        body[id="other"] .nonmatch-probe {width:111px;}
        #ownmail-email-content body.main .already-scoped-probe {width:121px;}
        body.main+.outside, body.main ~ .outside,
        body.main /* comment */ + .outside {opacity:0;}
        body.main .class-probe::before {content:"<b>literal</b>";}
    """
    expected = {
        "class": "21px",
        "attribute": "31px",
        "exact": "41px",
        "id": "51px",
        "child": "61px",
        "data": "71px",
        "cascade": "81px",
        "nonmatch": "9px",
        "already-scoped": "9px",
    }
    body = "".join(f'<div class="probe {name}-probe">{name}</div>' for name in expected)
    stylesheet = f"<style>{css}</style>"
    source = (
        f"<html><head>{stylesheet if style_location == 'head' else ''}</head>"
        '<body class="main compact" id="message" data-layout="wide">'
        f"{stylesheet if style_location == 'body' else ''}{body}</body></html>"
    )
    message = EmailMessage()
    message["Subject"] = "Synthetic qualified body styles"
    message["From"] = "sender@example.com"
    message.set_content(source, subtype="html")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        r"""
        const expected = __EXPECTED__;
        const reference = await browser.newPage();
        try {
            // Only synthetic CSS/text: no scripts, resources or mailbox content.
            await reference.setContent(__SOURCE__);
            for (const [name, width] of Object.entries(expected)) {
                const selector = '.' + name + '-probe';
                assert.equal(await reference.locator(selector).evaluate(el => getComputedStyle(el).width), width);
                assert.equal(await page.locator('#ownmail-email-content ' + selector)
                    .evaluate(el => getComputedStyle(el).width), width, name + ' must retain original matching/cascade');
            }
            const before = el => getComputedStyle(el, '::before').content;
            assert.equal(await page.locator('#ownmail-email-content .class-probe').evaluate(before),
                await reference.locator('.class-probe').evaluate(before));
        } finally {
            await reference.close();
        }
        await page.evaluate(() => {
            const outside = document.createElement('div');
            outside.className = 'outside';
            outside.id = 'outside-qualified-control';
            outside.innerHTML = '<div class="probe class-probe" style="width:123px">App shell</div>';
            document.getElementById('ownmail-email-content').after(outside);
        });
        await settle();
        const outside = page.locator('#outside-qualified-control');
        assert.equal(await outside.evaluate(el => getComputedStyle(el).opacity), '1', 'Root siblings must stay outside sender scope');
        assert.equal(await outside.locator('.probe').evaluate(el => getComputedStyle(el, '::before').content), 'none');
        assert.equal(await page.locator('#ownmail-email-content').evaluate(el => el.classList.contains('main')), false);
        assert.equal(await page.locator('#ownmail-email-content').getAttribute('data-layout'), null);
        """.replace("__EXPECTED__", json.dumps(expected)).replace("__SOURCE__", json.dumps(source)),
        theme="light",
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


@pytest.mark.parametrize(
    "css_text",
    [
        pytest.param('<!--.probe::before {content: "wrapped";}-->', id="adjacent-wrapper"),
        pytest.param(' \n<!--\n.probe::before {content: "wrapped";}\n-->\n ', id="spaced-wrapper"),
        pytest.param(
            '/* reset <p> margins; <!-- quoted --> */ .probe::before {content: "<b> <!-- literal --> </b>";}',
            id="markup-comment-and-string",
        ),
        pytest.param(
            r""".probe::before {content: "<style | \<style | \\<style | \\\<style | \\\\<style | \3c b>";}""",
            id="escape-parity",
        ),
        pytest.param(
            r""".probe::before {content: "\3c /StYlE><img id='css-injected' src='x' onerror='window.cssInjected=1'><ScRiPt>window.cssInjected=2</ScRiPt>";}""",
            id="escaped-style-closing-string",
        ),
        pytest.param(
            "/* </StYlE-not-an-end-tag><img id='css-injected' src='x' onerror='window.cssInjected=1'> */"
            ' .probe::before {content: "safe";}',
            id="style-closing-comment",
        ),
    ],
)
def test_markup_like_styles_preserve_rendered_css_and_cannot_escape(
    shell_app, contrast_browser, spacing_sanitizer, css_text
):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=False)
    # Keep the shared rules inside genuine outer wrappers, when present.
    rules = ".probe {width:47px;border-top:7px solid black;} @media (400px < width <= 900px) {.probe {width:73px;}}"
    if css_text.lstrip().startswith("<!--"):
        css_text = css_text.replace("<!--", "<!--" + rules, 1)
    else:
        css_text += rules
    message = EmailMessage()
    message["Subject"] = "Synthetic stylesheet"
    message["From"] = "sender@example.com"
    message.set_content(
        f'<style>{css_text}</style><div class="probe">Message copy</div><p id="after-style">After style</p>',
        subtype="html",
    )
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        r"""
        const authoredCSS = __CSS__;
        await page.evaluate(css => {
            const outside = document.createElement('div');
            outside.id = 'outside-probe';
            outside.className = 'probe';
            outside.textContent = 'App shell control';
            document.body.append(outside);
            // textContent gives the browser the original CSS without HTML parsing.
            // A shadow root isolates this benign reference from sender/app styles.
            const host = document.createElement('div');
            host.id = 'css-reference';
            document.body.append(host);
            const shadow = host.attachShadow({mode: 'open'});
            const style = document.createElement('style');
            style.textContent = css;
            const probe = document.createElement('div');
            probe.className = 'probe';
            probe.textContent = 'Reference';
            shadow.append(style, probe);
        }, authoredCSS);
        for (const width of [600, 1100]) {
            await page.setViewportSize({width, height:900});
            await settle();
            const result = await page.evaluate(() => {
                const read = el => ({
                    width: getComputedStyle(el).width,
                    border: getComputedStyle(el).borderTopWidth,
                    content: getComputedStyle(el, '::before').content
                });
                return {
                    actual: read(document.querySelector('#ownmail-email-content .probe')),
                    reference: read(document.querySelector('#css-reference').shadowRoot.querySelector('.probe')),
                    outside: read(document.querySelector('#outside-probe'))
                };
            });
            assert.equal(result.reference.width, width === 600 ? '73px' : '47px');
            assert.equal(result.reference.border, '7px');
            assert.notEqual(result.reference.content, 'none');
            assert.deepEqual(result.actual, result.reference, 'Sanitized CSS must preserve browser string/escape meaning');
            assert.equal(result.outside.border, '0px', 'Sender selectors must remain scoped');
            assert.equal(result.outside.content, 'none');
        }
        const content = page.locator('#ownmail-email-content');
        assert.equal(await content.locator('.probe').count(), 1);
        assert.equal(await content.locator('.probe').textContent(), 'Message copy');
        assert.equal(await content.locator('#after-style').textContent(), 'After style');
        assert.equal(await content.locator('script, img, #css-injected, [onerror]').count(), 0);
        assert.equal(await page.evaluate(() => window.cssInjected), undefined);
        """.replace("__CSS__", json.dumps(css_text)),
        theme="light",
        viewport=(600, 900),
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("quoted", [False, True])
def test_body_background_covers_trailing_content_and_keeps_images_blocked(
    shell_app, contrast_browser, spacing_sanitizer, theme, quoted
):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=True)
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "sender@example.com"
    background_url = "https://fixture.test/background.svg"
    if quoted:
        background_url = "&quot;" + background_url + "&quot;"
    message.set_content(
        '<html><body style="background-color:#eef1f4;margin:0;padding:0;'
        f'background-image:url({background_url})" onload="unsafe()">'
        '<table width="100%" bgcolor="#eef1f4" cellpadding="0" cellspacing="0">'
        '<tr><td style="height:400px;padding:24px">Message copy</td></tr></table>'
        '<img id="tail" width="1" height="1" src="https://fixture.test/pixel.svg">'
        "</body></html>",
        subtype="html",
    )
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        """
        const content = page.locator('#ownmail-email-content');
        const shellBackground = await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor);
        for (const width of [390, 1440]) {
            await page.setViewportSize({width, height:900});
            await settle();
            assert.equal(await content.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(238, 241, 244)');
            assert.equal(await content.evaluate(el => getComputedStyle(el).padding), '0px');
            assert.equal(await content.getAttribute('onload'), null);
            const root = await content.boundingBox();
            const table = await content.locator('table').boundingBox();
            assert(root.height > table.height, 'The trailing inline image must leave a line below the table');
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            assert.equal(await content.evaluate(el => {
                const r = el.getBoundingClientRect();
                const bottom = document.elementFromPoint(r.x + r.width / 2, r.bottom - 1);
                return getComputedStyle(bottom).backgroundColor;
            }), 'rgb(238, 241, 244)', 'The sender canvas must paint the line below its table');
            assert.equal(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor), shellBackground);
        }
        assert(!requests.has('https://fixture.test/pixel.svg'));
        assert(!requests.has('https://fixture.test/background.svg'));
        assert((await content.evaluate(el => getComputedStyle(el).backgroundImage)).includes('https://fixture.test/background.svg'));
        """,
        theme=theme,
        viewport=(390, 900),
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )
