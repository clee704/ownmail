---
id: TASK-130
title: Restrict trust-sender redirects to local paths
status: Done
assignee: []
created_date: '2026-10-10 05:31'
updated_date: '2026-10-10 05:51'
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
- [x] #1 Protocol-relative values (`//host`), values with a scheme or network location, and values containing a backslash or control characters fall back to the default response; a plain local path still redirects there. Removing the unused field instead is acceptable if its tests are updated.
- [x] #2 A test-client regression posts synthetic `//attacker.invalid` and `/\attacker.invalid` values and asserts no response redirects off the origin; the protocol-relative case fails against the current startswith("/") check.
- [x] #3 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
trust_sender now accepts a redirect value only when _is_local_path holds: it starts with one slash, not two or more, and contains no backslash or control character. Anything else falls back to '/', the existing default response (JSON after a saved trust, a redirect to '/' otherwise). Before the fix, '//host' and '/<tab>/host' both produced 'Location: //host'; Werkzeug happened to encode the backslash and collapse '///', but the check no longer relies on that. get_back_to_search_url shares the backslash and control-character check through _has_ambiguous_url_characters; its own behavior is unchanged. No other route builds a redirect from request input. Removed a JSON branch in trust_sender that tested for an empty redirect value, which could never occur. The redirect field was kept, validated, as the task allowed; nothing in the repository sends it, so removing it remains an option.

The full pre-push gate passed with browser tests running (none skipped).
<!-- SECTION:NOTES:END -->
