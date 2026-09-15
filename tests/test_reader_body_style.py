"""Sender body styling at the reader boundary."""

from email.message import EmailMessage

import pytest

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("quoted", [False, True])
def test_body_background_covers_trailing_content_and_keeps_image_controls(
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
        assert.equal(await content.getAttribute('data-bg-urls'), 'https://fixture.test/background.svg');
        await page.locator('#load-images-btn').click();
        await settle();
        assert.equal(await content.getAttribute('data-bg-urls'), null);
        assert((await content.evaluate(el => getComputedStyle(el).backgroundImage)).includes('https://fixture.test/background.svg'));
        assert(requests.has('https://fixture.test/background.svg'));
        assert(requests.has('https://fixture.test/pixel.svg'));
        """,
        theme=theme,
        viewport=(390, 900),
        rendered_page=response.get_data(as_text=True),
    )
