---
id: TASK-93
title: Recognize HTML layouts beyond inline root backgrounds
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-15 02:56'
updated_date: '2026-09-30 12:45'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The padding detector still misses sender backgrounds supplied by scoped CSS classes or nested beyond the first wrapper child. Synthetic cases include a class-styled root canvas, a background table under multiple div wrappers, and a background applied only to a table cell. Recognize these authored layouts without removing readable padding from simple HTML or changing sender markup. TASK-94 now carries the body style onto the reader container; the remaining body attributes and body-qualified selectors are tracked in TASK-56.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Synthetic class-styled and nested layout canvases render without a second reader frame in both themes.
- [ ] #2 Simple HTML retains readable padding, including messages with decorative or hidden background elements.
- [ ] #3 Browser checks exercise the real sanitizer at phone and desktop widths and fail against the previous behavior.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve review base 87878bce4c0d90a9b161312894b42815180a5af6 on fresh isolated branch fix/authored-layout-padding. Commit this task-only claim and plan before code; preserve completed TASK-119/TASK-56 and main.
2. Extend existing actual-worker and reader-spacing regression families. Establish the five verified red cases: class-styled root canvas, deeply wrapped background table, background on the principal layout cell, decorative inline badge beside ordinary copy, and nested hidden background beside ordinary copy. Keep existing inline-root/simple/root-hidden controls plus class-hidden and class-decorative controls.
3. Limit production edits to worker padding classification. Inspect an ephemeral reader-equivalent structure of already-sanitized markup/CSS so scoped classes can be recognized. Identify a visible main layout canvas through transparent wrappers/table structure, excluding hidden/decorative backgrounds; retain padding when classification is genuinely ambiguous. Do not change returned sender markup, selector rewriting, dark-mode classification, DOMPurify/CSS protection settings, remote loading or trust behavior. No new dependencies or unrelated policy.
4. Run synthetic worker red/green and existing sanitizer checks while TASK-12 owns Chromium. Once released, extend the existing actual-route browser matrix at 390/768/1440 widths in both themes, preserving simple HTML/plain-text insets, authored spacing, containment and print behavior. Prove browser regressions against the unchanged worker; do not use jsdom geometry as browser evidence.
5. Review the complete diff against the original base, obtain fresh independent Astra Ultra correctness/UI review, resolve findings, then run the full required pre-push gate with mandatory browsers and unchanged thresholds/assertions. Update only verified acceptance criteria and close with normal hooks/clean local commits. No main, merge/rebase, publication, denied TASK-37/95/111/125 work, real mail/settings/credentials. Escalate new design ambiguity before expanding scope.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Branch: fix/authored-layout-padding. Exact review base: 87878bce4c0d90a9b161312894b42815180a5af6 (completed TASK-56, includes preserved TASK-119). At preflight, TASK-93 was To Do/unassigned with no dependencies and follows TASK-56 in the execution order; prerequisite TASK-92/TASK-94 are Done. Read-only premise on this exact base used the actual unchanged Node worker and actual body extraction: all three requested authored canvases incorrectly return needsPadding=true despite preserved backgrounds/copy; decorative inline and nested-hidden backgrounds incorrectly return false. Five inline/simple/class-hidden/decorative controls pass. These are classification/structure results, not claimed browser geometry. The existing detector samples two root elements and their first children and ignores scoped classes; its parsed document lacks the final reader wrapper. Owned files: ownmail/sanitizer/worker.js (padding classification only), tests/test_sanitizer.py, tests/test_reader_spacing.py and this task ledger. No source implementation yet. Fresh independent Astra Ultra correctness/UI review required. TASK-12 currently owns Chromium; private Node/static work can proceed after the plan checkpoint. Next action: commit this task-only claim/plan before code.

Implemented a padding-only static classifier on an ephemeral standards-mode reader DIV. It uses already-sanitized CSS and literal scoped type/class/ID descendant/child relationships, normalizes individual declarations without relying on jsdom cascade specificity, and requires an identifiable visible canvas containing the message copy. Returned markup, selector rewriting, dark-mode metadata and sanitizer/trust behavior are unchanged. Hidden/decorative/competing layout regions and uncertain CSS retain padding; supported backgrounds are demonstrably solid paint. Direct trailing inline images preserve the existing spacing harness behavior without admitting block/floating/positioned image regions. No new dependency or owner policy.

Red evidence on the unchanged worker: all five requested defects reproduce in actual-worker regressions (five failed subtests, seven passing controls) and the existing actual-route reader-spacing matrix (five failed cases, eleven passing controls). Original geometry/assertions at 390/768/1440 in both themes remain unchanged. The browser red run exited and released its interval; TASK-115 subsequently requested the interval. No further Chromium launch has occurred.

Fresh independent Astra Ultra review requested corrections before final validation: a combinatorial descendant matcher (719-byte input exceeded a six-second external probe while base completed in 0.309 seconds), uncertain modern/clip/masked paint, hidden/zero-sized content, competing image/table regions and uppercase CSS keywords. Author review additionally found sender BODY attributes affecting ephemeral matching, non-CSS style types and escaped declaration ambiguity. Regression evidence is preserved. Corrections memoize element/selector states, bound selector proof to the actual reader root, remove discarded BODY attributes from the disposable projection, ignore non-CSS style blocks, normalize supported keywords and default uncertain paint/visibility/structure to padding. Source is stabilized for independent re-review; no findings are claimed closed until that review returns.

Current focused validation: 120 sanitizer tests pass, including all exact task cases, returned-markup assertions, retained TASK-56/TASK-119 tests, review regressions and a bounded subprocess performance regression. Node syntax, Ruff check, Ruff format-check, deptry and diff checks pass. All task acceptance criteria remain unchecked pending green browser geometry and full required pre-push validation. Next action: finish independent re-review and checkpoint the implementation with normal hooks, then run green rendered/full gates after the coordinated Chromium interval is available. No integration, publication or real mailbox/settings operations.

Independent Astra Ultra re-review passed on implementation checkpoint 4213693f9c544b3381220a4d31069cf46140b3cb: all five findings resolved, no open correctness/UI issue. Fifty-four independent probes pass; the previous matcher timeout reproduction now completes in 0.216 seconds. All 54 differential comparisons preserve byte-identical sanitized HTML and unchanged dark-mode metadata; TASK-56/TASK-119 protections remain unchanged. Reviewed worker SHA-256: d665180fd6d20fb89155ada950e68fdba802266beaa2faa6a613de4f67ba66e9. Author self-review and normal checkpoint commit hooks also pass. Chromium process verification found no task-owned process; the interval is released for TASK-115. Remaining prerequisite: coordinated browser availability for green reader-spacing checks and the full mandatory pre-push gate; no acceptance criterion or Done status is claimed yet. No new design-policy blocker. Next action: resume rendered validation on this clean checkpoint after TASK-115 exits.
<!-- SECTION:NOTES:END -->
