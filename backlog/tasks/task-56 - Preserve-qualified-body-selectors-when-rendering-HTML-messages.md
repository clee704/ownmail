---
id: TASK-56
title: Preserve qualified body selectors when rendering HTML messages
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-13 06:30'
updated_date: '2026-09-30 12:08'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CSS sanitizer scopes a selector such as body[class=main] .logo under the reader container, but body extraction removes the matching body element. Since TASK-94, _extract_body_content copies the body's style onto #ownmail-email-content; its class, id, bgcolor, and other attributes are still dropped, so body.main and body[class=main] selectors never match. Preserve the authored selector relationship without allowing styles to affect the app shell.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A synthetic message with a qualified body selector retains the intended descendant styling after sanitization and body extraction.
- [x] #2 The preserved styles remain scoped to message content.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve review base e234cbd69c909e16a404467480819601e9888189 on isolated branch fix/body-qualified-selectors. Commit this TASK-56-only claim and plan before code. Preserve all completed worktrees and main.
2. Add actual-worker and synthetic rendered regressions for body.main, body[class=main], body#message and combined/static qualifier cases. Prove failure on the unchanged base, including nonmatching controls, specificity/cascade, descendant/child relationships, head/body style placement and outside app controls.
3. Limit production edits to worker.js. Resolve supported static initial body qualifiers against the sanitized body, preserving selector specificity when mapping to the existing message container. Keep provenance for head styles until BODY attribute sanitization completes; do not reinterpret sender-authored already-scoped selectors, copy attributes to the app wrapper or add layout wrappers. Keep unsupported dynamic selectors unchanged and never introduce root sibling selectors that reach app elements.
4. Preserve TASK-119 preparation/string/escape/style-closing behavior, source-map suppression, DOMPurify protection/settings, existing CSS filters and unrelated scoping paths. Test removed/clobbering IDs, successive worker requests and malformed selectors. No web/template/config/schema/credential/dependency changes, security relaxation, denied TASK-37/95/125 work or real mail/network operations. Escalate any requirement that cannot fit this bounded scope safely.
5. Run focused worker/browser tests, repository lint/format/deptry, author self-review against the original base and a fresh independent Astra Ultra correctness/security review. Run the complete required pre-push gate with mandatory isolated browser coverage and unchanged assertions/thresholds, using the coordinated browser interval. Close only verified criteria with normal hooks and a clean local branch; no merge/rebase/main/publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Branch: fix/body-qualified-selectors. Review base: e234cbd69c909e16a404467480819601e9888189 (completed TASK-119). TASK-56 is To Do, unassigned, dependency-free and immediately follows TASK-119 in the recorded execution order. The actual current worker plus body extraction reproduced the premise: an unqualified body descendant selector retains its one match; body.main, body[class=main] and body#message each match the original synthetic document once and the extracted rendered structure zero times. The sanitized body retains these attributes; extraction intentionally transfers only style. Merely deleting qualifiers would activate nonmatching rules and lose cascade specificity; adding an inner wrapper would alter layout. The bounded plan instead evaluates static predicates against the sanitized body and retains their specificity inside the existing message scope, with original-source provenance for head styles. The existing sanitizer protection boundary remains intact. Owned files: ownmail/sanitizer/worker.js, tests/test_sanitizer.py, tests/test_reader_body_style.py and this task record. No new dependency, STOP-category behavior or owner-policy change is planned. Independent fresh Astra Ultra review is required. Next action: commit this claim/plan before implementation.

Implemented bounded static leading body qualifier resolution in worker.js. Class, ID and attribute predicates are evaluated only after DOMPurify sanitizes body attributes. Matching compounds are mapped to the existing reader container while retaining their specificity and original descendant/child suffix. Original head stylesheet sources are retained weakly until sanitized body context is available, preserving sender-authored already-scoped selector behavior. No attributes are copied into the app wrapper and no layout wrapper is added. Root sibling relationships, nonmatches, dynamic pseudo-classes and escaped/unsupported root compounds keep the existing fallback.

Red/green evidence: the unchanged actual worker failed 20 new subtests while 25 controls passed; both rendered head/body cases failed on lost qualified styling. With the implementation, all 110 sanitizer tests and all 12 body-style browser cases pass, including the complete retained TASK-119 cases. New coverage checks class/ID/attribute/combined/uppercase predicates, exact attribute values, ID-versus-class cascade, head/body placement, extraction structure, sanitized-away IDs/event attributes, author-scoped provenance, unsupported syntax, root sibling exclusion, and successive request isolation. Browser assertions compare authored synthetic CSS with actual route output and unchanged outside controls. Repository Ruff check, Ruff format-check, deptry and diff checks pass. Author self-review against the original base confirms the four approved paths only. Independent fresh Astra Ultra security/correctness review and the complete pre-push gate remain pending. No integration, publication or real mailbox operations performed.

Independent Astra Ultra review found three P2 correctness issues in implementation checkpoint 03a405ff957a35bd9e560ea13fed8fff044c3822 before the full gate. (1) Head body-style predicates ran before final inline CSS cleanup. This is fixed by resolving BODY after sanitizeInlineStyle in the existing hook; a regression first failed two head subcases, then all 111 sanitizer tests passed. (2) jsdom accepts malformed numeric/hyphen class/ID/unquoted attribute tokens, and the forgiving :is projection activates rules browsers reject. Two actual-route browser regressions reproduce this: width becomes 106px instead of the original 17px. (3) jsdom falsely matches absent attributes against null-like values and class/ID names, empty substring operands and non-ASCII token whitespace; static predicate evaluation needs a bounded browser-faithful correction. Findings (2) and (3) remain open. The first implementation's green core tests are not final validation; the new malformed-selector browser tests currently fail.

The last focused browser run exited and its interval was released for the queued TASK-64 full gate. No TASK-56 full gate has started. Current work remains In Progress, with original base and checkpoints preserved. Next action: replace the forgiving projection with a fail-closed specificity-preserving form, correct bounded static predicate matching, obtain fresh review of the full revised diff and rerun focused/full browser gates when the interval is available. No main changes or publication.

All three independent-review findings are now resolved in the revised implementation. BODY resolution follows inline cleanup (R1). Matching rules use nonforgiving :not(body-compound) on the fixed existing DIV reader container, retaining specificity without making invalid selectors valid (R2). A bounded literal static predicate evaluator replaces jsdom.matches entirely (R3): identifier/attribute grammar, absent attributes, all attribute operators, empty operands, ASCII token whitespace, ASCII-only comparison, source-document quirks class/ID semantics, and HTML default/explicit attribute case rules follow HTML/Selectors semantics. Escaped, dynamic, namespaced and otherwise unsupported root syntax retains the existing fallback. No new trust or compatibility policy, dependencies, DOM attributes, layout wrapper or sanitizer setting is introduced.

Revision evidence: all 116 sanitizer tests and all 22 actual-route body-style browser cases pass. The new predicate tests first reproduced 50 failing worker subtests with 106 controls passing; all eight new predicate browser cases also fail against the preserved pre-fix worker and pass on the revision. Earlier core, inline-hook and malformed-selector red evidence remains preserved. Original-browser comparisons verify absence/null behavior, ASCII versus NBSP tokens, empty operands, case rules, syntax validity and unchanged outside controls. Repository Ruff check/format-check, deptry and diff checks pass. Fresh independent Astra Ultra re-review resolved all three P2s and found no new correctness/security issue; it reran the original 85 probes and passed 80 additional asserted boundary cases. Author self-review against the original TASK-119 base confirms only the approved four files changed. The full pre-push gate remains pending.

Normative matching references: https://html.spec.whatwg.org/multipage/semantics-other.html#case-sensitivity-of-selectors and https://www.w3.org/TR/selectors-4/#attribute-selectors . Browser evidence independently verifies the implemented cases.
<!-- SECTION:NOTES:END -->
