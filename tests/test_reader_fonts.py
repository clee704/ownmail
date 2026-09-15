"""Sender fonts through MIME parsing, sanitization, and browser loading."""

import base64
from email.message import EmailMessage

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


def test_sender_stylesheet_and_embedded_fonts_load_in_reader(shell_app, contrast_browser, spacing_sanitizer):
    app, archive = shell_app
    app.config.update(sanitizer=spacing_sanitizer, block_images=True, auto_scale=True)
    font_paths = list(
        test_email_contrast.SANITIZER_DIR.glob("node_modules/playwright-core/lib/vite/recorder/assets/codicon-*.ttf")
    )
    assert font_paths, "Playwright's bundled font is required for this browser check"
    font_uri = "data:font/ttf;base64," + base64.b64encode(font_paths[0].read_bytes()).decode()
    stylesheet_url = "https://fonts.googleapis.com/css?family=SenderFixture"
    external_css = f'@font-face {{font-family: "Sender Fixture"; src: url("{font_uri}");}}'
    glyphs = "&#xea60;" * 30
    body = f"""<!doctype html><html><head>
        <link rel="stylesheet" href="{stylesheet_url}">
        <style>@font-face {{font-family: "Embedded Fixture"; src: url("{font_uri}");}}</style>
        </head><body style="margin:0;padding:0">
        <div id="sender-copy" style="font-family: 'Sender Fixture', monospace; font-size:24px;
            display:inline-block; white-space:nowrap">
            <a id="sender-link" style="font-family:inherit !important">{glyphs}</a>
        </div>
        <div id="embedded-copy" style="font-family: 'Embedded Fixture', monospace">&#xea60;</div>
        </body></html>"""
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "reader@example.com"
    message.set_content("Synthetic plain text alternative")
    message.add_alternative(body, subtype="html")
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
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        """
        const loaded = await page.evaluate(async () => {
            const glyph = String.fromCodePoint(0xea60);
            const sender = await document.fonts.load('24px "Sender Fixture"', glyph);
            const embedded = await document.fonts.load('16px "Embedded Fixture"', glyph);
            return [sender, embedded].map(faces => faces.map(face => face.status));
        });
        assert.deepEqual(loaded, [['loaded'], ['loaded']], 'Both sender font sources load');
        assert.equal(requests.get('https://fonts.googleapis.com/css?family=SenderFixture'), 1);
        assert.equal(await page.locator('#sender-link').evaluate(el => getComputedStyle(el).fontFamily),
            await page.locator('#sender-copy').evaluate(el => getComputedStyle(el).fontFamily),
            'Linked copy inherits the sender font');
        await settle();
        const viewport = await page.locator('#ownmail-email-viewport').boundingBox();
        const copy = await page.locator('#sender-copy').boundingBox();
        assert(copy.width <= viewport.width + 1, 'Loaded font fits the reader');
        assert.equal(await page.locator('#ownmail-fit-message').evaluate(el => el.hidden), false);
        """,
        theme="light",
        viewport=(390, 900),
        rendered_page=response.get_data(as_text=True),
        external_stylesheets={stylesheet_url: external_css},
    )
