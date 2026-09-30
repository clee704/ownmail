---
id: TASK-126
title: Preserve correctly declared Cyrillic body text during validation
status: To Do
assignee: []
created_date: '2026-09-30 04:50'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Short correctly declared Windows-1251 Cyrillic body text is rejected by the body readability whitelist and falls back to Latin-1. Verified before TASK-40 at c44eb0f620d79e9be10ff8449969408adac6341b in display and parser/indexing. The whitelist excludes Cyrillic; this separate task owns that existing gap.

Synthetic reproduction (no archive required):

```python
import email
from email.policy import default
from ownmail.parser import EmailParser
from ownmail.web import _decode_text_body

text = "Привет"
payload = text.encode("cp1251")
raw = b"Content-Type: text/plain; charset=windows-1251\r\n\r\n" + payload
part = email.message_from_bytes(raw, policy=default)
assert _decode_text_body(payload, "windows-1251") == text
assert EmailParser._safe_get_content(part) == text
assert EmailParser.parse_file(content=raw)["body"] == text
```

Actual baseline result: `Ïðèâåò` instead of `Привет`. The HTML variant, wrapping the same bytes in `<p>...</p>` with text/html, also fails. Keep existing wrong-charset recovery, UTF-8 preservation and header behavior when addressing declared legacy validation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Synthetic plain and HTML Windows-1251 bodies preserve Cyrillic in display and indexing.
- [ ] #2 Existing wrong-charset recovery and valid UTF-8 body behavior remain intact with the required repository checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Manager-approved follow-up discovered during TASK-40 baseline guard preparation. No implementation started.
<!-- SECTION:NOTES:END -->
