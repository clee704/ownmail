---
id: TASK-117
title: Block remote fonts and media while images are blocked
status: In Progress
assignee: []
created_date: '2026-09-29 05:40'
updated_date: '2026-09-29 12:05'
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
- [ ] #1 With blocking on and an untrusted sender, browser tests confirm the covered fonts and media make no remote requests
- [ ] #2 Loading images or trusting the sender restores the covered content, and the banner and docs describe what blocking covers
- [ ] #3 Sanitizer comments match the enforced font policy and the full pre-push gate passes
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
