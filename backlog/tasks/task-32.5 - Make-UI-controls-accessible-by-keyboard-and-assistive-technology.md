---
id: TASK-32.5
title: Make UI controls accessible by keyboard and assistive technology
status: Done
assignee: []
created_date: '2026-09-12 18:33'
updated_date: '2026-09-12 21:31'
labels:
  - ui
  - ux
dependencies: []
parent_task_id: TASK-32
priority: medium
ordinal: 5
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Give existing controls meaningful names and predictable keyboard behavior. Search and sort lack explicit labels, selection checkbox labels are empty, and the message action button consists of three empty spans. Menus toggle visually without exposing expanded state or handling Escape. Browser accessibility inspection confirms unnamed selection controls and an unnamed detail action button.

Cover the shared shell, search results, message detail, Trash and Settings. Add accessible names, appropriate button/link semantics, selected and expanded state, visible keyboard focus and reliable menu focus handling. Use shared styles from TASK-32.1 when available; these functional fixes can land independently of the visual redesign. This task owns interaction semantics, while the component tasks own layout and appearance.

Evidence: ownmail/templates/base.html, search.html, _email_list.html, email.html, trash.html and settings.html.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Search, sort, pagination, icon-only actions, row selection and select-all have meaningful accessible names; row selection identifies its message.
- [x] #2 Menus and navigation work with keyboard activation and Escape, expose expanded/selected state, and return focus to the triggering control on dismissal.
- [x] #3 Every interactive control has visible keyboard focus in both themes, and hidden menu/sidebar content does not leave unexpected keyboard stops.
- [x] #4 Keyboard-only checks cover search, open message, return, select, cancel and menu actions; browser accessibility inspection verifies names, states and selection feedback across the affected templates.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accessible names identify search, sort, row selection, select-all, pagination and icon-only controls. Current destinations use aria-current; menus and navigation expose state and return focus after Escape. Hidden drawer content is inert. Browser accessibility inspection and keyboard checks covered search, open, return, select, cancel, navigation and menu activation. Mixed selection and selection counts are announced, and focus outlines were checked against both themes. Native Message details and More disclosures retain keyboard behavior. Regression tests exercise menu movement, focus return, hidden content and collapse-state transitions.

Final validation: pre-commit run -a --hook-stage pre-push passed, including formatting, dependency checks and the full test suite with its coverage gate. Implementation committed in a7d6062.
<!-- SECTION:NOTES:END -->
