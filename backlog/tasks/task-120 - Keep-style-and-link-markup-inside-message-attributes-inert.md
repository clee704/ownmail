---
id: TASK-120
title: Keep style and link markup inside message attributes inert
status: Done
assignee: []
created_date: '2026-09-29 12:31'
updated_date: '2026-09-29 17:05'
labels:
  - ui
dependencies: []
priority: high
type: bug
ordinal: 9600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_extract_body_content collects a message's <style> and <link> tags by matching the sanitized HTML string, so markup that DOMPurify keeps as inert attribute text can become live elements:

- A <link> written inside an attribute value is prepended to the message as a live element with the attributes the sender wrote. An event-handler attribute on it runs when the message opens, whether or not remote content is blocked: loaded messages carry no CSP, and the blocking policy allows inline handlers because the reader uses them. Confirmed in Chromium through the real sanitizer and message route; an independent check also navigated the page to a remote host this way.
- A <style> start tag inside an attribute value pairs with a later real </style>, so the message markup and text between them become one style element.

Both reproduce with synthetic messages, and the matching predates TASK-117. Collect style and link elements from the parsed document instead of the serialized string. Removing 'unsafe-inline' from the blocking policy's script-src would also stop injected handlers while blocked, but the reader's inline scripts and handlers would have to move first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Style and link markup written inside attribute values stays attribute text after body extraction, and the message's real style and link elements keep their cascade order
- [x] #2 A browser test confirms that an event handler written inside an attribute this way does not run, with remote content blocked and loaded
- [x] #3 The full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Replace regex-based wrapper and style/link extraction with a single stdlib HTMLParser pass over the sanitizer output. Preserve serialized start tags, text, entity references, style/link order, and the body style attribute without reserializing HTML5 void elements through lxml. Extend the existing unit and browser regressions to body/html/head attributes, prove they fail on the current extractor, and run reader layout/font tests plus the full pre-push gate. Review the completed repair before committing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed in ownmail/web.py: _extract_body_content now delegates style/link collection to _split_style_and_link_elements, which walks the markup one tag at a time (STYLE_LINK_TOKEN_RE consumes each tag's quoted attribute runs). A <link> or <style> the sanitizer keeps as inert attribute text is swallowed by its enclosing tag, so it is no longer lifted into a live element; real style/link elements keep document (cascade) order. Body content stays string-based rather than re-serialized through lxml, which would have regressed void elements such as <source> inside <picture>. Comment handling was left out because DOMPurify strips comments before this runs. Tests: two unit cases in tests/test_web.py and a browser test in tests/test_image_blocking.py asserting the injected onload/onerror never fires with remote content blocked and loaded; all three fail against the pre-fix code. Full pre-push gate green at 96.44% coverage.

Review of f76d495 on 2026-09-29: reopened because AC 1 and AC 2 are incomplete. The new style/link scan fixes the original paragraph-attribute case, but _extract_body_content still finds the body boundary with a regex that ignores quoted attribute values (ownmail/web.py:399). A greater-than sign followed by link markup inside a body title attribute is emitted as a live link. A body start marker followed by link markup inside an html or head title attribute has the same result.

Verified all three wrapper-attribute variants through the real DOMPurify worker, synthetic MIME messages, the message route, and Chromium. The link handler executes both with remote content blocked and loaded; browser requests were intercepted by the existing fixture. Blocking prevents the stylesheet request but still allows its error handler. Compared with the exact extractor at 1084a8e: these paths predate f76d495, so this is an incomplete fix, not a new regression.

The 61 extraction and image-blocking tests pass with OWNMAIL_REQUIRE_BROWSER_TESTS=1. All three tests added by f76d495 fail when the exact parent extractor is substituted in memory, confirming that those tests detect the original bug. They do not cover wrapper attributes. Extend the existing regression cases to body/html/head attributes and extract body boundaries from parsed tags before marking this task Done. Preserve style/link order and HTML5 void elements.

Targeted validation: OWNMAIL_REQUIRE_BROWSER_TESTS=1 .venv/bin/pytest tests/test_web.py::TestExtractBodyContent tests/test_image_blocking.py -q. Browser setup prerequisites remain in CONTRIBUTING.md. This review does not implement the remaining fix.

Full suite verification with required browser tests: 3,909 passed, 1 expected failure; coverage 96.44%.

Repair in progress: replaced both the style/link scan and wrapper regexes with one HTMLParser pass over sanitized output. It keeps serialized start tags and entity references, collects real style/link elements in order, and copies only the body style attribute. This avoids lxml reserialization of HTML5 void elements and removes the unsafe body-boundary slicing.

Extended the existing browser regression to paragraph, body, html, and head attributes in blocked and loaded modes. Added unit cases for wrapper attributes, void elements, and entity preservation; strengthened existing tests for body styling, CSS containing tag-like text, and fragments. Before the repair, all six wrapper unit cases, the body-style case, and all three added browser cases failed. They pass after the repair, along with reader fonts, body backgrounds, and spacing. Deliberate in-memory faults in entity decoding and source-element handling make both new preservation tests fail; no source mutations were left behind.

Independent review found no remaining attribute-to-markup defect under the sanitizer contract. Its whitespace observation reproduced with a body using white-space:pre: a newline between head and body entered the message. Body parsing now clears only content collected before the real body start. The strengthened full-document test fails without this correction and passes with it, preserving whitespace inside the body.

Repair complete. Full pre-push gate passed with browser tests required; coverage 96.45%. The parser, regression tests, and task record are included in the repair commit.
<!-- SECTION:NOTES:END -->
