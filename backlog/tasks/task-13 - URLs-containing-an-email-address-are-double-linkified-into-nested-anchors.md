---
id: TASK-13
title: URLs containing an email address are double-linkified into nested anchors
status: To Do
assignee: []
created_date: '2026-07-24 21:07'
labels: []
dependencies: []
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_linkify("https://example.com/unsubscribe?email=user@example.com") emits:

    <a href="https://example.com/unsubscribe?email=<a href="mailto:user@example.com" ...>user@example.com</a>" ...>

An anchor nested inside another anchor's href attribute. The link is broken in the rendered message view. Unsubscribe/preference URLs carrying an email parameter are common, so this shows up on real mail.

Cause: the guard in _linkify_line (ownmail/web.py:775) is

    last_href = preceding.rfind('href="')
    last_close = max(preceding.rfind('>'), preceding.rfind('"'))
    if last_href > last_close: return email_addr   # skip

last_close picks up the opening quote of href=" itself, which always sits after the href= position, so last_href > last_close is never true and the skip never fires.

Not an injection risk: _linkify escapes its input before substituting, so only its own markup is malformed. Note this body path does NOT pass through the DOMPurify sanitizer (web.py:1607 vs 1579), so nothing downstream repairs it.

Fix candidates: linkify emails first then URLs, or do a single combined pass with one alternation regex so matches cannot nest.

tests/test_web.py::TestLinkify::test_email_inside_url_is_not_double_linked is marked xfail(strict=True) and will fail once this is fixed -- remove the marker then.

Found while writing web tests for TASK-3.
<!-- SECTION:DESCRIPTION:END -->
