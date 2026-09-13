---
id: TASK-57
title: Add a per-message appearance override for broken dark styles
status: To Do
assignee: []
created_date: '2026-09-13 06:47'
updated_date: '2026-09-13 07:12'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Preserve useful sender-authored dark styling while allowing a reader to display a broken HTML message in its base/light appearance without changing the app theme.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 HTML messages retain coordinated sender-authored dark styling by default; no blanket disabling or sender-specific exception is introduced.
- [ ] #2 A per-message control selects the sender's base/light appearance independently of app and system themes, preserves explicit sender colors, and can return to following the app theme.
- [ ] #3 The override preserves responsive CSS conditions, image controls, sizing and style scoping; plain-text messages continue following the app theme.
- [ ] #4 Synthetic browser regressions cover working dark variants and white-on-white or pale-on-white failures, including both app and system themes; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Comparisons against real messages show that authored dark variants often coordinate backgrounds, text, links and inset panels successfully. A blanket fixed-light policy would discard useful rendering. The recommendation is revised to preserve native dark support and provide a per-message base/light appearance override for broken templates.

The sample included both fully readable dark variants and partial failures within otherwise readable messages. One template used white text over an unchanged white panel; another had pale text in white callouts. These are template-specific findings, not a reason to disable dark rendering for every sender or message. A small selected sample does not establish prevalence.

Messages were rendered through the actual Flask view, sanitizer, stylesheet and theme code at a phone-sized width in WebKit 26.5. Text/background pairs and screenshots were compared in light and dark app modes. Remote images and fonts were blocked; this checks local text/CSS behavior, not every asset or a physical iPhone. Gradient-backed sections were visually checked because background-color alone can give a misleading contrast estimate.

Implementation should retain coordinated sender dark styles by default. The override must select the sender's base/light variant without changing the app theme or recoloring explicitly styled content, and allow returning to theme-following behavior. Handle compound, nested and negated theme conditions without losing responsive layout rules. The existing regex theme rewriting and qualified-body-selector defect (TASK-56) are separate implementation concerns; avoid blanket dark-style removal or per-brand exceptions.

Earlier research still applies to the override: a plain color-scheme: light container does not reliably suppress document media queries. A full iframe has broader isolation benefits but requires image-control and sizing changes, plus browser verification. Sources: [CSS color adjustment](https://drafts.csswg.org/css-color-adjust-1/), [media-query semantics](https://www.w3.org/TR/mediaqueries-5/), [WebKit iframe support](https://bugs.webkit.org/show_bug.cgi?id=284973), [Outlook message appearance](https://support.microsoft.com/en-us/outlook/mail/dark-mode-in-outlook), [Apple Mail message backgrounds](https://support.apple.com/guide/mail/change-viewing-settings-cpmlprefview/mac).

Research only. Rendering code is unchanged and acceptance criteria remain unverified.
<!-- SECTION:NOTES:END -->
