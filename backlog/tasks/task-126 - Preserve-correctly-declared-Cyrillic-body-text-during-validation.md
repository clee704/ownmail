---
id: TASK-126
title: Preserve correctly declared Cyrillic body text during validation
status: In Progress
assignee:
  - '@codex-ic2'
created_date: '2026-09-30 04:50'
updated_date: '2026-09-30 13:56'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 26900
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
- [x] #1 Synthetic plain and HTML Windows-1251 bodies preserve Cyrillic in display and indexing.
- [ ] #2 Existing wrong-charset recovery and valid UTF-8 body behavior remain intact with the required repository checks.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 598844182834e7be611a8465829c4e9566010cd4 (completed TASK-8); isolated branch fix/declared-cyrillic-bodies.
1. Add the manager-authorized TASK-126 row immediately after TASK-123 in doc-4, preserving every existing row, and align this task ordinal before code changes.
2. Extend existing body-charset regressions with declared Windows-1251 Cyrillic plain/HTML display, MIME-part and indexing cases. Preserve known wrong-charset, other legacy, UTF-8/U+FFFD and header controls; demonstrate the reported cases fail on the review base.
3. Add only the bounded Cyrillic character class needed by body readability validation. Retain replacement-character and control-garbage rejection, the existing ratio, codec order and header behavior. Escalate if this needs broader classification policy.
4. Self-review and obtain a fresh Astra Ultra correctness review, run focused synthetic/parser/web checks and the complete required pre-push browser/coverage gate with private runtime state, then commit verified closure. No integration or publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Manager-approved follow-up discovered during TASK-40 baseline guard preparation. Fresh premise on this review base: Windows-1251 Привет becomes 厥外奄 in both plain and HTML display/part decoding/indexing; the earlier Latin-1 result in the description is the historical pre-TASK-40 baseline. Four synthetic preservation controls pass, including correctly decoded Cyrillic headers. No real archive or messages were used.
Manager explicitly authorized local doc-4 placement after TASK-123, this task ledger, parser body readability and existing charset regression families only. TASK-123 and completed branches remain separate. Pending owner decisions and all existing execution-order rows are preserved. Scope excludes header decoding, fallback-order changes, arbitrary Unicode acceptance, dependencies, schema, credentials, real messages and security settings.

Implementation: body readability now counts the bounded Cyrillic U+0400-U+04FF block, including letters used by Windows-1251. The existing readability ratio, sampling length, U+FFFD rejection/strict UTF-8 handling, control-garbage checks and codec precedence/order are unchanged; header code is untouched.
Red evidence: six new plain/HTML charset cases failed against the unchanged product while 22 controls passed. Green focused validation: 536 parser/web/body tests passed, with one existing expected failure; only the six browser-rendered charset cases were deferred to the full required gate. The shared matrix verifies display wrappers, MIME-part decoding and indexing for Windows-1251, its cp1251 alias and Cyrillic UTF-8 with literal U+FFFD, alongside all existing legacy/wrong-charset controls. New UTF-8 and cp1251 control-garbage cases remain rejected. Ruff check, format --check, deptry and diff checks pass. Author self-review is complete; fresh independent Astra Ultra review and full browser/coverage gate remain pending before closure.
<!-- SECTION:NOTES:END -->
