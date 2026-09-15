---
id: TASK-92
title: Remove the outer frame from HTML messages
status: In Progress
assignee: []
created_date: '2026-09-15 02:39'
updated_date: '2026-09-15 02:56'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
HTML messages inherit the reader article horizontal padding, leaving an extra app-colored frame around sender-authored layouts on phones. Let authored HTML use the available reader width while retaining readable spacing for plain text and simple HTML. Check zero-margin HTML, authored spacing, wide-message fitting, themes, and desktop containment.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sender-authored HTML reaches the reader edges on phones without adding an app-colored frame, and remains contained on desktop.
- [x] #2 Plain text and simple HTML retain readable insets; sender-authored margins and padding are preserved, including explicit zero margins.
- [ ] #3 Browser regressions cover phone and desktop layouts, both themes, and wide-message fitting; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The HTML viewport now extends across the article inset. Simple HTML keeps its previous total horizontal text inset (24px on phones, 40px on desktop), plain text remains unchanged, and sender body CSS can override fallback padding. Print resets the shared inset to zero.

Integrated route tests exercise MIME parsing and the real sanitizer. Seven synthetic cases pass in Chromium and WebKit at 390px, 768px, and 1440px in both themes, with print containment checks. The pre-fix stylesheet fails the HTML edge assertions while plain text passes. Deliberately breaking fallback padding and plain-text spacing also fails the corresponding checks. A WebKit screenshot verifies that a synthetic newsletter reaches both reader edges.

The existing delayed-image fit assertion assumed a narrower canvas; it now verifies that the fitted image fills its actual viewport. All reader scroll and navigation checks pass. Independent review found no actionable issue.

Inspection of the installed iOS 26.5 Mail formatter shows an early BODY padding rule that sender styles can override. Exact native padding and physical-device rendering were not verified. Existing body-attribute extraction is tracked in TASK-56; these tests cover stylesheet body rules and inline wrapper styles.

Implementation committed in acfa264. The full pre-push gate passed with required Chromium browser tests enabled: 2,798 passed, one expected failure, and 95.97% coverage. WebKit spacing and reader-scroll checks also passed.

Follow-up: a real HTML message still receives fallback padding because two hidden preview blocks consume the detector limit before the visible background table. Reopened to skip non-rendered leading elements and add a regression using that structure. Existing geometry checks did not cover hidden preheaders.

The follow-up fix excludes inline display:none elements from the layout sample without altering the message HTML. Both positive and inverse regressions failed before the fix and pass in Chromium and WebKit afterward. A read-only replay of the reported real message verifies that its gray canvas reaches both reader edges at three widths in both themes, with external resources blocked. Other CSS-class and deep-wrapper detection limits are tracked separately.
<!-- SECTION:NOTES:END -->
