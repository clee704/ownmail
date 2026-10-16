"""The reader's message frame document as the server renders it."""

from unittest.mock import MagicMock

from lxml import html

from tests import test_email_contrast
from tests.conftest import create_test_app, message_content, mock_archive_db

shell_app = test_email_contrast.shell_app
QUOTED_TEXT = 'Quote " and &quot; and "><img id=breakout>'


def render(tmp_path, body):
    (tmp_path / "message.eml").write_text(
        "From: sender@example.com\nSubject: Synthetic frame\nContent-Type: text/html\n\n" + body
    )
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.db = mock_archive_db()
    archive.db.get_email_by_id.return_value = ("message", "message.eml", None, None, None, None)
    response = create_test_app(archive).test_client().get("/email/message")
    assert response.status_code == 200
    return response.data.decode()


def test_message_frame_is_sandboxed_without_scripts(tmp_path):
    page = render(tmp_path, "<p>Synthetic message</p>")
    tree = html.fromstring(page)
    (frame,) = tree.xpath('//iframe[@id="ownmail-email-frame"]')
    assert frame.get("sandbox").split() == ["allow-same-origin", "allow-popups", "allow-popups-to-escape-sandbox"]
    assert frame.get("title") == "Message"
    assert tree.get_element_by_id("ownmail-fit-message").get("aria-controls") == frame.get("id")


def test_quotes_in_message_text_stay_inside_the_frame_document(tmp_path):
    body = (
        '<p id="quoted">Quote &quot; and &amp;quot; and &quot;&gt;&lt;img id=breakout&gt;</p>'
        '<p id="after-quote">After the quote</p><img id="real-image" alt="">'
    )
    page = render(tmp_path, body)
    tree = html.fromstring(page)
    assert len(tree.xpath("//iframe")) == 1
    assert tree.xpath('//*[@id="ownmail-email-content" or @id="quoted" or @id="after-quote"]') == []
    assert tree.xpath('//*[@id="breakout" or @id="real-image"]') == []
    content = message_content(page)
    assert content.get_element_by_id("quoted").text_content() == QUOTED_TEXT
    assert content.get_element_by_id("after-quote").text_content() == "After the quote"
    assert len(content.xpath('.//img[@id="real-image"]')) == 1


ESCAPES = (
    '<p><a id="top-link" href="http://ownmail.test/top-link" target="_top">Top link</a></p>'
    '<form method="post" action="http://ownmail.test/form-post"><button id="post">Post</button></form>'
    '<form action="http://ownmail.test/form-top" target="_top"><button id="get-top">Get</button></form>'
)


def test_frame_blocks_top_navigation_and_forms(shell_app, browser_node):
    """Unsanitized markup, rendered straight into the reader template, still cannot leave the frame."""
    app, _ = shell_app
    test_email_contrast.run_contrast_browser(
        app,
        browser_node,
        ESCAPES,
        "",
        """
        const start = page.url();
        for (const control of ['#top-link', '#post', '#get-top']) {
            await message().locator(control).click({timeout: 2000});
            await settle();
            await page.waitForTimeout(300);
            assert.equal(page.url(), start, control);
        }
        const escaped = [...requests.keys()].filter(url => /top-link|form-/.test(url));
        assert.deepEqual(escaped, []);
        assert.equal(page.frames().filter(frame => frame.url() === 'about:srcdoc').length, 1);
        assert.equal(await message().locator('#top-link').count(), 1);
        await page.locator('#ownmail-message-details-toggle').click();
        assert.equal(await page.locator('#ownmail-message-metadata').isVisible(), true);
        // WebKit reports each blocked top-level navigation as a page error.
        const blocked = 'The frame attempting navigation of the top-level window is sandboxed';
        errors.splice(0, errors.length, ...errors.filter(error => !error.includes(blocked)));
        """,
        theme="light",
    )
