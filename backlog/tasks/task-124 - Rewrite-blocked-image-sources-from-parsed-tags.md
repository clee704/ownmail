---
id: TASK-124
title: Rewrite blocked image sources from parsed tags
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-30 03:15'
updated_date: '2026-09-30 07:12'
labels:
  - ui
dependencies: []
priority: high
type: bug
ordinal: 9650
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_hide_blocked_images (ownmail/web.py) finds img and source tags by matching IMAGE_TAG_RE against the sanitized HTML string, the approach TASK-120 removed from _extract_body_content. The pattern does not skip quoted attribute values, so image-tag text that the sanitizer keeps inside another element's attribute is matched and rewritten as if it were a tag: IMAGE_TAG_RE.findall('<p title="<img src=a.png>">x</p>') returns one match. The sanitizer's serializer leaves < and > unescaped in attribute values, so such text reaches this function, which runs whenever remote content is blocked, before body extraction.

Found while auditing TASK-120. At minimum the rewrite alters attribute text the sender wrote; whether it can also change the element structure the browser sees has not been checked. Rewrite from parsed tags, as _MessageBodyParser does, so only real img and source elements change, and keep serialized markup intact rather than reserializing through lxml.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Image-tag text inside an attribute value is left unchanged, while real img and source elements still get the placeholder and lose remote srcset values as before
- [x] #2 A regression test through the real sanitizer and message route shows attribute text containing image markup reaching the page unchanged with remote content blocked, and real remote images staying unrequested
- [ ] #3 The full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Use the observable synthetic premise already reproduced through the real sanitizer, message route and Chromium. Preserve the original task example as a passing control; positive failures cover image/srcset attribute overlap and false cross-tag matches. Review base: 5028a03374b972b2e9365ee0b6b82ed19fa49c73.
2. Restrict rewriting to parsed real img/source tags and actual attribute tokens. Preserve the sanitizer's serialized markup and untouched attributes/text rather than reserializing through lxml. Keep existing remote URL/srcset policy and CSP behavior, and leave sanitizer installation/locking/recovery, run_server and body extraction outside this task.
3. Add focused regressions in tests/test_image_blocking.py that fail on the base implementation. Assert inert attribute and DOM preservation, correct real image placeholders and removal of remote srcset, unchanged non-image media attributes, and browser requests through the real sanitizer and route. Preserve existing image-blocking and loaded-state assertions.
4. Run focused checks in private runtime state and self-review the full task diff. Incorporate any later reviewed TASK-127 changes only through coordinator-approved integration, then run the complete required-browser coverage/pre-push gate and normal closing hooks on the final combined base. Update criteria only from evidence and leave public push/default-branch changes to coordination.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Branch: fix/parsed-image-blocking. Exact claim/review base: 5028a03374b972b2e9365ee0b6b82ed19fa49c73, the reconciliation candidate; TASK-127 full review/gate is still pending and this claim does not approve it. TASK-16 and its completed worktree remain preserved.
Premise correction: the original <p title="<img src=a.png>"> example is unchanged after rewriting; an outer-regex match alone is not a failure. Tests through the real sanitizer and /email route instead prove five failures: a real img with alt="<img src=" keeps its remote src; analogous img and source srcset values survive; a false source span skips a real image placeholder; a false img span wrongly replaces a video src. Three controls pass, including the original example. Chromium confirms the src and source-srcset failures while inert attributes remain unchanged and zero-request checks pass under CSP. No DOM-structure corruption or network escape is claimed. Each case includes a genuine remote trigger that is correctly rewritten, proving the blocking path executed.
The image helpers and test_image_blocking.py are identical between the tested upstream fd7f8af0810ab273310947e46b5e8f88c3fb9e8f and the exact claim base. This is a bounded correctness/layout fix in web.py _hide_blocked_images and its image-tag/attribute parsing helpers, tests/test_image_blocking.py and this task only. Shared README, sanitizer setup/locking/recovery, run_server, credentials, real mail and dependencies are excluded. No fetch, main change, rebase or push occurred. The synthetic reproduction was reported before implementation.
Next action: commit this task-only plan with normal hooks, then implement the approved narrow parser change. Later reviewed TASK-127 fixes must be present in the final combined gate before closure.

The implementation now uses HTMLParser callbacks to locate only real img/source start tags and tokenizes complete sanitizer-serialized attributes before rewriting actual src/srcset values. Source spans are replaced directly in the original string, retaining unrelated attributes, text, comments, entities, case and line endings. The old global image-tag and URL-attribute regexes were removed. No production nodes outside the owned image helpers changed, and sanitizer/run_server/body extraction/README/config are unchanged. On the original implementation, ten new unit and real-sanitizer route cases failed while two original controls passed; the first sandboxed run could not launch the browser probe, then the same checks ran under narrow headless-test escalation without changing assertions. With the fix, all focused image-blocking and web tests passed: 401 passed, one existing TASK-13 expected failure. Mandatory Chromium covered the new exact DOM/attribute/src/srcset/request assertions as well as existing Load/Block/Trust behavior. Repository-wide Ruff check, format-check and deptry pass. Author self-review found no actionable introduced issue. AC1 and AC2 are verified; AC3 and closure remain pending the full gate on the final candidate incorporating any later reviewed TASK-127 fixes.

Validation checkpoint: the first full required-browser pre-push run completed with 3,873 passing tests, one existing TASK-13 expected failure and 96 setup errors. Every error is the same Chromium launch probe timing out after 30 seconds; no product assertion failed. Ruff, format, dependency and hygiene hooks passed. An unchanged direct retry of both new browser regressions then passed in 4.18 seconds. The coordinated reconciliation gate observed the same startup problem. No test assertions or browser requirements were weakened. AC3 remains unchecked while the common browser startup condition is diagnosed; next action is rerunning the complete required gate after that condition is resolved. TASK-127 independent review passed on the exact claim base without source changes; its final closure checkpoint still needs explicit ancestry and product-equivalence verification.
<!-- SECTION:NOTES:END -->
