---
id: TASK-67
title: Review sanitizer dependency audit findings
status: Done
assignee: []
created_date: '2026-09-13 19:07'
updated_date: '2026-09-29 06:41'
labels: []
dependencies: []
priority: high
type: chore
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A development install reported npm audit findings in the existing sanitizer dependency tree: DOMPurify, PostCSS, nanoid and ws. Verify the advisories against installed and supported versions, assess exposure in the sanitizer worker, and apply bounded dependency updates with regression coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Advisories and sanitizer exposure are documented against the dependency versions in use.
- [x] #2 Applicable dependency fixes are validated by sanitizer regressions and the full pre-push gate, with any remaining findings explained.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 674574f.
1. Record each advisory against the installed tree (DOMPurify 3.3.1, PostCSS 8.5.6, nanoid 3.3.11, ws 8.19.0) and against what a fresh install resolves, and assess whether the worker's configuration and the message page can reach it.
2. Raise the package.json floors to the validated DOMPurify and PostCSS releases, reinstall the development tree from scratch, and confirm npm audit is clean.
3. Parse message CSS with map: false so a sourceMappingURL comment in untrusted CSS never reaches the filesystem, including on installs whose node_modules predates the update.
4. Regression: an integration test showing a sourceMappingURL comment cannot make the worker read a local file; compare sanitizer output before and after the update over the test fixtures and existing cases; run the browser contrast tests and the full pre-push gate.
Out of scope: refreshing node_modules on existing installs when package.json changes (to be filed separately).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
When the task started, the development tree had DOMPurify 3.3.1, PostCSS 8.5.6, nanoid 3.3.11 through PostCSS and ws 8.19.0 through jsdom 26.1.0. npm audit listed 27 advisories: 18 for DOMPurify, 4 for PostCSS, 3 for nanoid and 2 for ws. package-lock.json is not tracked, so a new install resolves the newest versions in range. With the old floors that already meant DOMPurify 3.4.16, PostCSS 8.5.28, nanoid 3.3.19 and ws 8.22.0, which clear every advisory. Installs whose node_modules predates the fixes keep the flagged versions.

Exposure was judged against the worker (string input and output, WHOLE_DOCUMENT, array ADD_TAGS and ADD_ATTR, uponSanitizeElement and afterSanitizeAttributes hooks, jsdom without scripts or subresource loading) and the reader, which embeds the output once inside a div:

- PostCSS source-map loading (GHSA-6g55-p6wh-862q, GHSA-r28c-9q8g-f849, GHSA-fxqj-rqcc-2cmp) was reachable. The worker parsed each style block with default options, so a sourceMappingURL comment naming a local path made it read that file. On 8.5.6 an existing file that is not a source map replaced the message CSS with /* CSS parse error */, while a missing path left the CSS intact. That is a file-existence oracle, which a remote font request can reveal to the sender even while images are blocked (TASK-117). PostCSS 8.5.23 stops the read when from is unset. The worker now also passes map: false, which covers installs that keep an older PostCSS.
- PostCSS unescaped </style> (GHSA-qx2v-qp2m-jg93) was not reachable. Parsed style text cannot contain its own end tag, the worker selector and font rewrites cannot create one, and in both DOMPurify versions the markup probe that runs after the uponSanitizeElement hook removes a style element whose text holds </.
- DOMPurify: 14 advisories need options or hook behavior the worker does not use: IN_PLACE (5), SAFE_FOR_TEMPLATES with DOM output (2), Trusted Types (1), function-form ADD_TAGS or ADD_ATTR (3), setConfig (1), a hook that mutates the allow-lists (1) and a configured CUSTOM_ELEMENT_HANDLING (1). GHSA-v9jr-rg53-9pgp and GHSA-cj63-jhhr-wcxv need an earlier prototype pollution, and the worker merges no input into objects. GHSA-v2wj-7wpq-c8vv and GHSA-h8r8-wccr-v5f2 need the output placed back inside a raw-text element such as noscript or xmp, which the reader does not do.
- nanoid (GHSA-28wg-ghj8-5hjv, GHSA-2v37-7h3g-55p8, GHSA-xwg4-73v4-xw9w) was not reachable: PostCSS calls the non-secure generator with a fixed size of 6.
- ws (GHSA-58qx-3vcg-4xpx, GHSA-96hv-2xvq-fx4p) was not reachable: it backs the jsdom WebSocket, and the worker never runs scripts.

package.json now requires DOMPurify ^3.4.16 and PostCSS ^8.5.28, the versions validated here; PostCSS 8.5.28 requires nanoid ^3.3.18. jsdom stays at ^26.0.0, and ws keeps the ^8.18.0 range jsdom declares because it is unreachable and a new install resolves 8.22.0. A fresh install and the updated development tree both audit clean.

The unchanged worker produced the same output on both trees for 229 of 234 inputs: 3 HTML fixture parts, 182 HTML strings from the test files and 49 synthetic edge cases. The 5 differences are attribute values holding a raw-text closing tag (</noscript, </xmp, </iframe, or </script inside a data: link), which DOMPurify 3.4.16 drops. PostCSS 8.5.28 also escapes <style, </style and <!-- in its output as \3c, so a style block whose CSS string holds <!-- is now kept where the old tree dropped it. map: false changes only CSS with an inline source-map comment, which is now kept rather than replaced by the parse-error comment.

test_ignores_css_source_map_comments sanitizes a style block naming a local .map file and one naming an inline data: map. Both subtests fail on the old tree without map: false, the inline one also fails on the new tree without it, and both pass with it on either tree. Sanitizer and contrast tests with required Chromium: 127 passed. Contrast and image-blocking tests in WebKit: 75 passed. Full pre-push gate with required browser tests: 3899 passed, 1 expected failure, 96.43% coverage.

Remaining: _ensure_deps installs only when node_modules is missing, so source checkouts and in-place upgrades keep flagged versions until npm install runs; pipx reinstall resolves current ones. map: false covers the one reachable advisory on those installs. Filed as TASK-118. The comparison also showed that a style block wrapped in <!-- --> or holding markup-like text, such as <p> in a CSS comment, is dropped whole on both trees. Filed as TASK-119.
<!-- SECTION:NOTES:END -->
