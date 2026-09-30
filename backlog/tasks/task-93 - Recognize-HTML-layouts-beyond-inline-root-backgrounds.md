---
id: TASK-93
title: Recognize HTML layouts beyond inline root backgrounds
status: Done
assignee:
  - Ownmail audit IC4
created_date: '2026-09-15 02:56'
updated_date: '2026-09-30 16:43'
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
- [x] #1 Synthetic class-styled and nested layout canvases render without a second reader frame in both themes.
- [x] #2 Simple HTML retains readable padding, including messages with decorative or hidden background elements.
- [x] #3 Browser checks exercise the real sanitizer at phone and desktop widths and fail against the previous behavior.
- [x] #4 An unmatched supported static selector inside conditional CSS does not add reader padding to an otherwise verified canvas; affecting conditional rules retain conservative padding.
- [x] #5 Audit follow-up receives independent review and the final combined repository gate before reclosure.
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

Final validation passed on clean checkpoint f8db26355e98877618c454451d4975bf5691e549 (product implementation 4213693f9c544b3381220a4d31069cf46140b3cb). All 16 actual-route reader-spacing cases pass at 390, 768 and 1440 pixels in both light/dark themes, retaining the original simple HTML/plain-text insets, authored geometry, containment, fitting and print assertions. The required pre-push gate exited 0: 4,076 passed, one pre-existing TASK-13 expected failure, no skips, and 96.65957098411658% combined statement/branch coverage against the unchanged 95% threshold. All 13 mandatory Chromium launch/close probes completed without timeout. The complete selection, existing timeouts/assertions and coverage threshold were preserved; maxfail=1 and a runtime-only observer supplied actionable diagnostics. Static checks and normal commit hooks pass.

All three acceptance criteria are now verified, including five preserved red reproductions on the previous behavior and the green rendered matrix. Independent Astra Ultra review remains approved on the exact validated worker/test bytes, with all five findings resolved and 54 passing differential probes preserving sanitized HTML/dark-mode output. Author self-review passed against the original TASK-56 base. Unsupported or uncertain CSS/layouts deliberately retain reader padding. Browser validation has exited and the interval is released. This closure changes only the task ledger; all product/test files remain byte-identical to the fully validated checkpoint. TASK-121 lifecycle hunks are untouched. No integration, merge/rebase, publication, real mail/settings or trust-policy change. Task complete.

Authorized audit follow-up, review base 47e54fd653f65a33b394f52207602476dc14126b, isolated branch fix/audit-reader-regressions. Existing closure evidence is preserved; this task is reopened only for verified audit findings. No real mail, providers, credentials or running systems; no dependency, schema or main-branch change. Independent review and final combined mandatory-browser gate remain with the coordinator/integration owner before reclosure. Plan: (1) extend existing sanitizer and real-reader spacing tests with a responsive rule whose static selector has no matching element; prove failure on the combined base; (2) use the existing matcher before marking a conditional rule uncertain and ignore proven no-target rules; (3) retain unsupported-selector and genuinely conditional layout fallbacks without adding a cascade framework; (4) run worker and leased browser checks with normal hooks and full-diff self-review, then hand off clean commits for independent review/combined gate.

Audit correction checkpoint: actual worker regressions fail at the combined base for both an unmatched @media rule and an unmatched style[media] rule, while six matching/unsupported controls remain conservatively padded. The fix uses the existing literal matcher to establish targets first and ignores proven no-target rules before conditional uncertainty. The focused real-worker set passes, including all matching/unsupported controls. The real-reader spacing matrix now includes the exact audited newsletter case; its browser check, independent review and final combined gate remain pending. No cascade engine, sender-markup rewrite or startup/runtime change was added.

The new real-reader test failed against exported unchanged combined-base production on the extra padding class. With the fix, the complete seventeen-case spacing matrix passes at phone/tablet/desktop widths, in both themes and print; all affected charset/spacing checks total 60 passes. The eight worker subcases retain conservative behavior for matching and unsupported selectors. AC4 is verified; independent review and the final combined repository gate remain pending. Browser commands exited and the interval was released.

Full-task author review against combined base 47e54fd653f65a33b394f52207602476dc14126b confirms the only production change is ordering existing static target matching before conditional uncertainty. Matching/unknown selector fallback, sanitized HTML, dark-mode metadata, and all sanitizer startup/runtime code are preserved. Worker and rendered red/green evidence is complete; independent review and the integration owner final combined required gate remain outstanding.

Preserve authored full-width/class/nested canvases while retaining padding for plain content. Known unmatched static selectors in conditional CSS no longer add a second reader frame; affecting and unsupported selectors retain conservative fallback. Independent source review and five separate Node cases passed; mandatory combined browser cases cover actual reader spacing. Final combined verification passed on 6f76b4398d83c6a6217a0e7049428d976e531c63: unchanged pre-commit run -a --hook-stage pre-push, mandatory Chromium enabled, 4163 tests passed in 287.30s, 96.72% aggregate branch-inclusive coverage against 95%. All normal hygiene, Ruff, formatting and deptry checks passed. Exact backend, reader and TASK-125 heads are ancestors; all merged source/test paths were checked against their reviewed contents. No real mail, credential changes or remote operations. The following closure commit changes task metadata only; code and tests remain the verified candidate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Preserve authored full-width/class/nested canvases while retaining padding for plain content. Known unmatched static selectors in conditional CSS no longer add a second reader frame; affecting and unsupported selectors retain conservative fallback. Independent source review and five separate Node cases passed; mandatory combined browser cases cover actual reader spacing. Combined required gate: 4163 passed, 96.72% coverage; implementation and independent review complete. Local integration is authorized; no public push.
<!-- SECTION:FINAL_SUMMARY:END -->
