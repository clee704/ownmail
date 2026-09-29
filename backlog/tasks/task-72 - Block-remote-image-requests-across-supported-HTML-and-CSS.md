---
id: TASK-72
title: Block remote image requests across supported HTML and CSS
status: Done
assignee: []
created_date: '2026-09-13 20:20'
updated_date: '2026-09-29 06:00'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The README review confirmed that rendered messages can retain active CSS image URLs and responsive image sources while image blocking is enabled. A synthetic message passed through the real sanitizer and Flask message route retains these sources, with no message-response CSP preventing requests. The blocked-images banner can therefore overstate the protection. Correct the blocking behavior without changing archived messages or weakening HTML sanitization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With image blocking enabled and an untrusted sender, browser tests confirm that supported HTML and CSS image sources make no remote requests.
- [x] #2 Explicitly loading images and trusting a sender restore intended image behavior; blocked-state feedback accurately describes the result.
- [x] #3 Regression cases include style-block images and responsive image sources, and the full pre-push gate passes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: a141835.
1. Enforce blocking in the browser: while images are blocked, the message response carries CSP img-src 'self' data:, which stops every remote image the sanitizer allows (img src/srcset, picture sources, background attributes, posters, CSS in style attributes and style blocks, protocol-relative forms).
2. Load images, Block images and trusting a sender reload the message with ?images=load|block (or the default after trusting), keeping return_to. Delete the client-side data-src/data-bg-urls restore code and the CSS rewrite it needed.
3. Detect remote image references over the sanitized document (attributes and CSS, fonts excluded) so the banner and menu appear whenever something is blocked.
4. Keep the transparent placeholder for remote <img> sources (and drop remote srcsets) so blocked images keep their authored size rather than collapsing to alt text; the placeholder is cosmetic, CSP is the guard.
5. Regression: Chromium test against the real sanitizer and a live Flask server covering each vector blocked, Load images, Block images and trust; unit tests for detection and route headers. Update README and docs/setup.md limitation text.
Out of scope: remote fonts and media, which image blocking does not cover (filed separately).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Found during TASK-69 documentation review using synthetic input only. No real archive or credentials were accessed, and no outbound image requests were sent. Documentation qualifies the existing limitation pending this fix.

Before the fix, a Chromium check through the real sanitizer and message route showed 9 of 13 supported image sources still requested with blocking on: background attributes, image-set(), input type=image, picture sources, video posters, scheme-relative URLs, srcset and style blocks.

While images are blocked, the message response now carries CSP img-src 'self' data:, so the browser refuses every remote image whichever HTML or CSS feature names it. Load images, Block images and Always trust this sender reload the message with ?images=load, ?images=block or the default, keeping return_to and replacing the history entry. The client-side data-src and data-bg-urls restore code and the CSS rewrite are deleted.

Remote <img> sources still become a transparent placeholder and remote srcsets are dropped, so blocked images keep their authored size; a CSP-blocked image otherwise collapses to its alt text. The banner and menu controls depend on detection over the sanitized document's image attributes, url() arguments and image-set() strings, ignoring fonts, imports, comments and the body background attribute the reader drops. The CSP applies whenever images are blocked, so a detection miss hides the Load control but loads nothing.

Chromium and WebKit regressions cover all 13 sources: none is requested while blocked, and Load images, Block images and trusting the sender request or re-block them, keeping return_to and showing the trust notice. Removing the CSP or the placeholder fails the new tests. Independent review found no bypass or markup injection; its finding that quoted URLs in selectors or content raised the banner was fixed and covered. Full pre-push gate with required browser tests: 3898 passed, 1 expected failure, 96.43% coverage.

Remote fonts and media still load while images are blocked, confirmed in Chromium with synthetic messages. Filed as TASK-117; README and docs/setup.md state the limit.
<!-- SECTION:NOTES:END -->
