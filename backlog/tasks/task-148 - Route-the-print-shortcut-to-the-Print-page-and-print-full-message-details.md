---
id: TASK-148
title: Route the print shortcut to the Print page and print full message details
status: Done
assignee: []
created_date: '2026-10-19 05:06'
updated_date: '2026-10-19 05:12'
labels: []
dependencies: []
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Cmd+P (Ctrl+P on other platforms) in the reader prints the reader page, which for HTML messages carries only a note pointing to the Print action (TASK-142 AC8), and shows the sender's name and date without the address or recipients, because the details block is hidden until expanded. Route the shortcut to the Print page, and make the reader's own print show the full details for File > Print and other paths the page cannot intercept.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Cmd+P on macOS and Ctrl+P elsewhere in the reader opens the message's Print page, as the menu's Print action does, and the browser's print dialog does not open over the reader; the other modifier, Shift or Alt variants, and Ctrl+P on macOS keep their browser behavior
- [x] #2 The shortcut also works while focus is in the message frame where the engine runs parent listeners there; the engines tested and any limit are recorded in the notes
- [x] #3 Printing the reader page itself shows From with the address, To and Date, without duplicating the byline
- [x] #4 Browser tests cover both and fail when the change is reverted
- [x] #5 The full pre-push gate passes with browser tests required
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Commit to master (no STOP-list area). 1. email-reader.js: a keydown handler on the reader and, once ready, the frame document clicks the menu's Print link for Cmd+P on macOS and iOS (Ctrl+P elsewhere). 2. style.css print rules show the hidden details block in place of the byline, without labels. 3. Browser tests in tests/test_reader_spacing.py; README; pre-push gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18 (maintainer request): TASK-142 decided that Cmd+P in the reader prints a note pointing to the Print action and rejected cloning the message into the application page at print time. Catching the shortcut was not considered then; it adds no message CSS to the application page.
- The handler matches event.key 'p', or KeyP when the layout reports a non-Latin character (Korean), so Dvorak's physical P key is not taken. Ctrl+P on macOS stays the text-field previous-line binding. A held key opens one tab.
- Engines: Chromium 145 and WebKit 26 (Playwright). The shortcut opens the Print page from the reader in both. With focus in the message frame (a text selection keeps it there), Chromium runs the parent's listener on the frame document and opens the Print page; WebKit runs no parent listener in the script-less frame, so the browser prints the reader with its note. Checked in the test by enabling the frame case for WebKit, which times out.
- Not covered: File > Print, the share sheet and the toolbar send no key, so they print the reader. Its print rules now show From with the address, To and Date in place of the byline, and still hide labels as before. Not checked in real Safari or Chrome windows: that the native print dialog stays closed after preventDefault, which Playwright cannot observe.
- Break-to-fail: both new checks failed before the change (popup timeout; details not visible). Removing the frame listener fails the Chromium frame case; removing the labels-term rule fails the labels check.
<!-- SECTION:NOTES:END -->
