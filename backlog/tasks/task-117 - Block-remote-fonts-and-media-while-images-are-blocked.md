---
id: TASK-117
title: Block remote fonts and media while images are blocked
status: Done
assignee: []
created_date: '2026-09-29 05:40'
updated_date: '2026-09-29 12:32'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 9500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Image blocking stops every remote image through the message response's CSP img-src (TASK-72), but other remote content still loads. The sanitizer keeps @font-face sources from any host and remote <video> and <audio> sources. A Chromium check with synthetic messages confirmed that the font and both media files were requested while images were blocked. The worker once allowed @font-face URLs only from trusted font providers; that check was lost when CSS url() was opened up for images, and the comment above scopeAndSanitizeCSS still describes it. Decide which remote fonts and media blocking should cover, including the trusted font providers, and enforce it in the same response policy and reader feedback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With blocking on and an untrusted sender, browser tests confirm the covered fonts and media make no remote requests
- [x] #2 Loading images or trusting the sender restores the covered content, and the banner and docs describe what blocking covers
- [x] #3 Sanitizer comments match the enforced font policy and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: f8fcb51.
1. While blocking is on, the message response CSP becomes default-src 'self' data: with script-src and style-src 'self' 'unsafe-inline', so the browser refuses every remote resource a message names: images, fonts, font stylesheets and audio and video. Trusted font providers are covered too: a request at open reveals the open whichever host receives it. The sanitizer's provider list only decides which remote stylesheets are safe to keep once content loads.
2. Detect remote fonts (@font-face sources, @import, kept <link> stylesheets) and media sources (video, audio, source and track src) as well as images, so the banner and menu appear whenever something is blocked.
3. The reader, settings and docs call this remote content: banner, Load and Block actions, trusted-sender hints, README, docs/setup.md and the CLI config comment. Internal ids, the images= parameter and the block_images key stay.
4. Sanitizer comments describe the enforced policy: remote url() values stay, including @font-face sources from any host, and the reader's CSP blocks them; @import and <link> keep only trusted font providers' stylesheets because remote stylesheets escape scoping.
5. Tests: detection cases for fonts, imports, links and media; the Chromium and WebKit regression gains @font-face, a trusted-provider <link> and @import, and video and audio sources, none requested while blocked and all restored by Load, re-blocked by Block, and restored by trusting the sender.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Blocking now covers every remote font and every remote audio and video source, including the trusted font providers' stylesheets and font files. A request made when a message opens reveals the open and the reader's address to whichever host receives it, so a host list cannot make it private. The sanitizer's provider list still decides which remote stylesheets are kept once remote content loads, because a remote stylesheet escapes selector scoping. @font-face sources from any host load with the rest of the remote content, as images do.

While blocking is on, the message response carries default-src 'self' data: with script-src and style-src 'self' 'unsafe-inline'. A probe in Chromium and WebKit found that listing img-src, font-src, media-src and style-src blocked the same requests; default-src also refuses any other fetch a sanitized message might make. The reader's own scripts, fetches and styles are same-origin or inline.

Detection now includes @font-face and @import URLs, bare-string imports, kept <link> stylesheets, and audio, video, source and track sources, so the banner and menu appear when a message's only remote content is a font or media file. The reader, settings, README, docs/setup.md, config.example.yaml and the CLI config comment call this remote content. Internal ids, the images= parameter and the block_images key are unchanged.

Before the fix, the extended Chromium regression recorded requests for all 8 new sources while blocked: an arbitrary-host font, a Google Fonts <link> and @import with their font files, and video, source and audio files. Chromium and WebKit now request none of the 21 sources while blocked; Load, Block and trusting the sender request or re-block all of them. Removing script-src from the policy, or any new detection path, fails a test. No browser requested a track source in the probe, so tracks are covered by the detection tests and the policy only.

Independent review found no remote request the new policy misses and no reader behavior it breaks; a blocked reader page loads without CSP violations. It found that body extraction turns <link> markup inside attribute text into a live element whose event handlers run with remote content blocked or loaded. That predates this task and is filed as TASK-120. CSS-escaped url() forms such as \75rl() are blocked by the policy but not detected, so the reader offers no Load control for them.

A probe of whether browsers DNS-prefetch link hostnames in messages, which CSP does not govern, was inconclusive: Playwright's Chromium resolved neither the link host nor a dns-prefetch control hint.

Full pre-push gate with required browser tests: 3906 passed, 1 expected failure, 96.43% coverage.
<!-- SECTION:NOTES:END -->
