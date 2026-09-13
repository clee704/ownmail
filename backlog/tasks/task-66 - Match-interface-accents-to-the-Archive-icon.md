---
id: TASK-66
title: Match interface accents to the Archive icon
status: Done
assignee: []
created_date: '2026-09-13 08:58'
updated_date: '2026-09-13 09:04'
labels:
  - ui
dependencies: []
type: enhancement
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the blue interface accent with golden yellow matching the Archive icon. Keep primary buttons, links, focus indicators, controls, and selection states readable in light and dark themes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Primary actions and selection states use a coordinated golden-yellow palette in both themes.
- [x] #2 Changed text and focus colors meet contrast targets on the app surfaces, and print output remains readable.
- [x] #3 Visual checks and the required repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Replaced blue accents with #edb928 gold, charcoal primary-button text, and warm selection backgrounds. Added a foreground accent token so light-theme links, focus rings, controls, and progress indicators use readable dark gold. Default links on white HTML-message canvases keep dark gold; sender-authored colors remain intact. Print overrides retain neutral fills and contrasting text. Computed contrast is at least 5.87:1 for accent text on app surfaces and 6.79:1 for primary-button text; selected muted text is 4.52:1 light and 4.88:1 dark. Visually checked desktop Settings and 390px mobile selection, focus, plain-message links, and HTML-message links in the in-app WebKit browser using synthetic mail.

The full pre-push gate passed after visual and contrast checks. No runtime dependencies or archived message files changed.
<!-- SECTION:NOTES:END -->
