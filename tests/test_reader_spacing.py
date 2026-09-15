"""Reader spacing through MIME parsing, sanitization, and browser layout."""

from email.message import EmailMessage

import pytest

from ownmail.sanitizer import HtmlSanitizer
from tests import test_email_contrast

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser


@pytest.fixture(scope="module")
def spacing_sanitizer(contrast_browser):
    sanitizer = HtmlSanitizer()
    sanitizer.start()
    try:
        assert sanitizer.available, "Reader spacing checks require the real HTML sanitizer"
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
            '<div style="display:none;background:#eef1f4">Hidden preview</div>'
            '<div style="display:none !important;background:#eef1f4">Hidden preview spacer</div>'
            '<p id="copy">Simple formatted message</p>',
            True,
            None,
            id="simple-html-after-hidden-backgrounds",
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
    shell_app, contrast_browser, spacing_sanitizer, body, needs_padding, copy_inset
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
    assert (b"ownmail-email-content-padded" in response.data) is needs_padding
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
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
                const copy = await box(plain ? '.ownmail-email-body' : '#copy');
                const expectedInset = plain ? inset :
                    (authoredInset === null ? (width <= 600 ? 24 : 40) : authoredInset);
                near(copy.x, article.x + expectedInset, 'Message copy left inset');
                assert(copy.x + copy.width <= article.x + article.width + 1,
                    'Message copy stays within the reader');
                if (!plain) {
                    const viewport = await box('#ownmail-email-viewport');
                    near(viewport.x, article.x, 'HTML viewport left edge');
                    near(viewport.width, article.width, 'HTML viewport fills the reader');
                    const panel = page.locator('#panel');
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
        await page.emulateMedia({media:'print'});
        await settle();
        const printedArticle = await box('.ownmail-email-detail');
        const printedBody = await box(plain ? '#ownmail-email-content' : '#ownmail-email-viewport');
        near(printedBody.x, printedArticle.x, 'Printed body left edge');
        near(printedBody.width, printedArticle.width, 'Printed body stays within the article');
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        """.replace("__PLAIN__", "true" if body is None else "false").replace(
            "__COPY_INSET__", "null" if copy_inset is None else str(copy_inset)
        ),
        theme="light",
        viewport=(390, 900),
        rendered_page=response.get_data(as_text=True),
    )
