"""Reader spacing through MIME parsing, sanitization, and browser layout."""

from email.message import EmailMessage

import pytest

from ownmail.sanitizer import HtmlSanitizer
from tests import test_email_contrast
from tests.conftest import message_content

shell_app = test_email_contrast.shell_app


@pytest.fixture(scope="module")
def spacing_sanitizer(browser_server):
    sanitizer = HtmlSanitizer()
    sanitizer.start()
    try:
        assert sanitizer.available, f"Reader spacing checks require the real HTML sanitizer: {sanitizer.error}"
        yield sanitizer
    finally:
        sanitizer.stop()


@pytest.mark.parametrize(
    ("body", "needs_padding", "copy_inset"),
    [
        pytest.param(
            '<table id="panel" width="100%" bgcolor="#eef1f4" cellpadding="0" cellspacing="0">'
            '<tr><td style="padding:24px"><p id="copy" style="margin:0">Newsletter copy</p>'
            "</td></tr></table>",
            False,
            24,
            id="newsletter",
        ),
        pytest.param(
            '<div style="display:none !important">Hidden preview</div>'
            '<div style="display:none">Hidden preview spacer</div>'
            '<table id="panel" width="100%" bgcolor="#eef1f4" cellpadding="0" cellspacing="0">'
            '<tr><td style="padding:24px"><p id="copy" style="margin:0">Newsletter copy</p>'
            "</td></tr></table>",
            False,
            24,
            id="newsletter-after-hidden-preheaders",
        ),
        pytest.param(
            "<style>@media (max-width:600px) {.unused {width:100%}}</style>"
            '<table id="panel" width="100%" bgcolor="#eef1f4" cellpadding="0" cellspacing="0">'
            '<tr><td style="padding:24px"><p id="copy" style="margin:0">Newsletter copy</p>'
            "</td></tr></table>",
            False,
            24,
            id="newsletter-with-unmatched-responsive-rule",
        ),
        pytest.param(
            '<div style="display:none;background:#eef1f4">Hidden preview</div>'
            '<div style="display:none !important;background:#eef1f4">Hidden preview spacer</div>'
            '<p id="copy">Simple formatted message</p>',
            True,
            None,
            id="simple-html-after-hidden-backgrounds",
        ),
        pytest.param(
            "<style>.canvas {background:#eef1f4;margin:0;padding:24px}</style>"
            '<div class="canvas" id="panel"><p id="copy" style="margin:0">Newsletter copy</p></div>',
            False,
            24,
            id="class-styled-root-canvas",
        ),
        pytest.param(
            '<div><div><div><table id="panel" width="100%" bgcolor="#eef1f4" '
            'cellpadding="0" cellspacing="0"><tr><td style="padding:24px">'
            '<p id="copy" style="margin:0">Newsletter copy</p></td></tr></table></div></div></div>',
            False,
            24,
            id="nested-background-table",
        ),
        pytest.param(
            '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            '<td id="panel" bgcolor="#eef1f4" style="padding:24px">'
            '<p id="copy" style="margin:0">Newsletter copy</p></td></tr></table>',
            False,
            24,
            id="background-on-layout-cell",
        ),
        pytest.param(
            '<p><span style="background:#eef1f4">Badge</span></p><p id="copy">Simple formatted message</p>',
            True,
            None,
            id="decorative-inline-background",
        ),
        pytest.param(
            '<div><span style="display:none;background:#eef1f4">Hidden preview</span></div>'
            '<p id="copy">Simple formatted message</p>',
            True,
            None,
            id="nested-hidden-background",
        ),
        pytest.param(
            "<style>.preview {display:none;background:#eef1f4}</style>"
            '<div class="preview">Hidden preview</div><p id="copy">Simple formatted message</p>',
            True,
            None,
            id="class-hidden-background",
        ),
        pytest.param(
            '<style>.badge {background:#eef1f4}</style><p><span class="badge">Badge</span></p>'
            '<p id="copy">Simple formatted message</p>',
            True,
            None,
            id="decorative-class-background",
        ),
        pytest.param(
            '<div id="panel" style="background:#eef1f4;margin:0;padding:0">'
            '<p id="copy" style="margin:0">Flush authored copy</p></div>',
            False,
            0,
            id="authored-zero-spacing",
        ),
        pytest.param(
            '<div id="panel" style="background:#eef1f4;margin:12px;padding:20px">'
            '<p id="copy" style="margin:0">Inset authored copy</p></div>',
            False,
            32,
            id="authored-spacing",
        ),
        pytest.param(
            "<style>body {margin:0;padding:0}</style>"
            '<p id="copy" style="margin:0">Sender overrides fallback spacing</p>',
            True,
            0,
            id="body-css-zero-spacing",
        ),
        pytest.param(
            '<style>body {margin:0}</style><p id="copy">Message with only its margin reset</p>',
            True,
            None,
            id="body-css-zero-margin",
        ),
        pytest.param('<p id="copy">Simple formatted message</p>', True, None, id="simple-html"),
        pytest.param(None, False, None, id="plain-text"),
    ],
)
def test_message_spacing_preserves_sender_layout_and_reader_insets(
    shell_app, browser_node, spacing_sanitizer, body, needs_padding, copy_inset
):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=True)
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "reader@example.com"
    message.set_content("Plain text message with a short second line.\nSecond line.")
    if body is not None:
        message.add_alternative(
            body + '<img src="https://fixture.test/image.svg" width="40" height="20" alt="Example">',
            subtype="html",
        )
    message.add_attachment(b"Synthetic attachment", maintype="text", subtype="plain", filename="example.txt")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = (
        "synthetic",
        "synthetic.eml",
        "2024-01-01",
        "hash",
        "sender@example.com",
        None,
    )
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    assert (
        "ownmail-email-content-padded" in message_content(response.data, plain=body is None).classes
    ) is needs_padding
    test_email_contrast.run_contrast_browser(
        app,
        browser_node,
        "",
        "",
        """
        const plain = __PLAIN__;
        const authoredInset = __COPY_INSET__;
        const near = (actual, expected, message) => assert(Math.abs(actual - expected) <= 1,
            `${message}: expected ${expected}, got ${actual}`);
        const box = selector => page.locator(selector).boundingBox();
        for (const width of [390, 768, 1440]) {
            await page.setViewportSize({width, height:900});
            for (const theme of ['light', 'dark']) {
                await setTheme(theme);
                const article = await box('.ownmail-email-detail');
                const inset = width <= 600 ? 16 : 24;
                near(article.width, Math.min(width, 800), 'Reader width');
                for (const selector of ['.ownmail-email-header', '.ownmail-attachments',
                    ...(plain ? [] : ['.ownmail-image-banner'])]) {
                    const element = await box(selector);
                    near(element.x, article.x + inset, `${selector} left inset`);
                    near(element.x + element.width, article.x + article.width - inset,
                        `${selector} right inset`);
                }
                const copy = await (plain ? page : message()).locator(plain ? '.ownmail-email-body' : '#copy').boundingBox();
                const expectedInset = plain ? inset :
                    (authoredInset === null ? (width <= 600 ? 24 : 40) : authoredInset);
                near(copy.x, article.x + expectedInset, 'Message copy left inset');
                assert(copy.x + copy.width <= article.x + article.width + 1,
                    'Message copy stays within the reader');
                if (!plain) {
                    const viewport = await box('#ownmail-email-viewport');
                    near(viewport.x, article.x, 'HTML viewport left edge');
                    near(viewport.width, article.width, 'HTML viewport fills the reader');
                    const panel = message().locator('#panel');
                    if (await panel.count()) {
                        const bounds = await panel.boundingBox();
                        const margin = authoredInset === 32 ? 12 : 0;
                        near(bounds.x, article.x + margin, 'Authored background left edge');
                        near(bounds.width, article.width - 2 * margin, 'Authored background width');
                    }
                    assert.equal(await page.locator('#ownmail-fit-message').evaluate(el => el.hidden), true,
                        'Fluid messages do not require scaling');
                }
                assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
                    'Message spacing must not cause horizontal page overflow');
            }
        }
        assert.equal(await page.locator('.ownmail-print-note').isVisible(), false, 'The note only prints');
        await page.emulateMedia({media:'print'});
        await settle();
        const printedArticle = await box('.ownmail-email-detail');
        const note = page.locator('.ownmail-print-note');
        if (plain) {
            const printedBody = await box('#ownmail-email-content');
            near(printedBody.x, printedArticle.x, 'Printed body left edge');
            near(printedBody.width, printedArticle.width, 'Printed body stays within the article');
            assert.equal(await note.count(), 0, 'Plain text prints without the Print page note');
        } else {
            assert.equal(await page.locator('#ownmail-email-viewport').isVisible(), false,
                'The message frame does not print');
            assert.equal(await note.isVisible(), true, 'The note points to the Print action');
        }
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        """.replace("__PLAIN__", "true" if body is None else "false").replace(
            "__COPY_INSET__", "null" if copy_inset is None else str(copy_inset)
        ),
        theme="light",
        viewport=(390, 900),
        rendered_page=response.get_data(as_text=True),
    )


def test_print_page_embeds_the_message_and_paginates(shell_app, browser_node, spacing_sanitizer):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True)
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message.set_content("Plain alternative")
    paragraphs = "".join(f"<p>Synthetic paragraph {index} with enough words to wrap.</p>" for index in range(150))
    message.add_alternative(
        f'<style>p {{ color: rgb(1, 2, 3); }}</style><div id="copy">{paragraphs}</div>'
        '<img src="https://fixture.test/image.svg" width="40" height="20" alt="Example">',
        subtype="html",
    )
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", "2024-01-01", "hash", "s", None)
    response = app.test_client().get("/print/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        browser_node,
        "",
        "",
        r"""
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            'The Print page fits a phone screen');
        await page.addInitScript(() => { window.print = () => { window.ownmailPrinted = (window.ownmailPrinted || 0) + 1; }; });
        await page.reload({waitUntil: 'load'});
        await settle();
        assert.equal(await page.evaluate(() => window.ownmailPrinted), 1, 'Loading the page opens the print dialog');
        await page.emulateMedia({media: 'print'});
        assert.equal(await page.locator('iframe').count(), 0);
        assert.equal(await page.locator('#ownmail-email-content #copy p').first().evaluate(p => getComputedStyle(p).color),
            'rgb(1, 2, 3)', 'Message CSS applies to the directly embedded message');
        assert.equal(await page.locator('img').evaluate(img => img.src.startsWith('data:')), true,
            'Remote content stays blocked');
        if (process.env.OWNMAIL_BROWSER_ENGINE === undefined || process.env.OWNMAIL_BROWSER_ENGINE === 'chromium') {
            const pdf = (await page.pdf({preferCSSPageSize: true})).toString('latin1');
            assert((pdf.match(/\/Type\s*\/Page\b/g) || []).length > 1, 'A tall message prints on several pages');
        }
        """,
        theme="light",
        viewport=(600, 900),
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )
