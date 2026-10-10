---
id: TASK-130
title: Restrict trust-sender redirects to local paths
status: To Do
assignee: []
created_date: '2026-10-10 05:31'
labels:
  - security
dependencies: []
references:
  - ownmail/web.py
priority: medium
type: bug
ordinal: 9860
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
trust_sender (ownmail/web.py) accepts any `redirect` form value that starts with "/". A protocol-relative value passes that check: a test-client POST with an empty email and `redirect=//attacker.invalid` returns 302 with `Location: //attacker.invalid`, which a browser resolves to another host. No template or script in the repository sends `redirect`; the reader posts with fetch and uses the JSON response.

This is a redirect-validation defect. No credential or cookie exposure has been shown.

Accept only a validated local path, or remove the field if nothing needs it. get_back_to_search_url already validates local targets with urlsplit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Protocol-relative values (`//host`), values with a scheme or network location, and values containing a backslash or control characters fall back to the default response; a plain local path still redirects there. Removing the unused field instead is acceptable if its tests are updated.
- [ ] #2 A test-client regression posts synthetic `//attacker.invalid` and `/\attacker.invalid` values and asserts no response redirects off the origin; the protocol-relative case fails against the current startswith("/") check.
- [ ] #3 The full pre-push gate passes.
<!-- AC:END -->
