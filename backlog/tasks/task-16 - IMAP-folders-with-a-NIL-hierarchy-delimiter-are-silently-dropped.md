---
id: TASK-16
title: IMAP folders with a NIL hierarchy delimiter are silently dropped
status: Done
assignee:
  - Ownmail backend audit
created_date: '2026-07-25 05:24'
updated_date: '2026-09-30 16:43'
labels: []
dependencies: []
priority: medium
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The LIST response parser (ownmail/providers/imap.py, parse_list_response) matches the delimiter as a quoted string: '\((?P<flags>.*?)\) "(?P<delim>.*?)" (?P<name>.*)'. RFC 3501 allows a server to report NIL instead of a quoted delimiter when the mailbox has a flat namespace with no hierarchy. Such lines fail the regex and are skipped entirely, so those folders are never scanned and their mail is never downloaded — a silent, total sync failure for that folder rather than a visible error.

Pre-existing; predates the role work in TASK-5.2, which only moved the regex into its own function. Current behaviour is pinned by tests/test_imap_provider.py::TestParseListResponse::test_skips_unparseable_lines.

Fix: accept NIL as well as a quoted delimiter, and treat it as an empty delimiter — roles.role_for_imap_folder already handles delimiter='' by matching the whole name. Consider also warning when a LIST line fails to parse, so a future shape mismatch is visible instead of silent.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Valid LIST rows with a NIL hierarchy delimiter produce the original folder name and flags with an empty delimiter; quoted-delimiter rows and mixed quoted/NIL listings retain their existing results.
- [x] #2 Non-byte entries, genuinely malformed rows and nonselectable folders retain the existing skip behavior; a valid NIL row is no longer classified as malformed.
- [x] #3 NIL folders use whole-name role matching and existing SPECIAL-USE, configured-folder and role-exclusion rules without changing those policies.
- [x] #4 Synthetic parser and mocked-provider regressions show eligible NIL folders reach archive listing/scanning and role discovery while excluded folders remain excluded; the valid-NIL regression fails against the original parser, with existing quoted-delimiter coverage preserved.
- [x] #5 NIL delimiter tokens are accepted regardless of ASCII case in parser and full/incremental mocked archive scans, while names, flags, quoted delimiters and exclusions remain unchanged.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Independently reconfirm the valid-NIL drop with synthetic LIST responses and inspect parse_list_response, the existing live parser, role matching and provider regression helpers.
2. Change only the archive LIST parser to accept NIL and return an empty delimiter, preserving quoted delimiters, names/flags and existing filtering. Reuse established conventions without refactoring the separate strict live lifecycle parser or changing role policy.
3. Replace the existing NIL-as-unparseable assertion with valid-NIL coverage and retain a genuinely malformed-input regression. Cover mixed listings, non-byte entries, nonselectable folders, flat whole-name role matching, configured exclusions, role discovery and eligible NIL folders reaching mocked archive scans.
4. Run focused provider/role tests, then the repository's complete coverage/browser/pre-push gate in the isolated worktree; self-review the full task diff, record results, and close this task with normal hooks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: still present in the archive download path (providers/imap.py LIST regex requires a quoted delimiter and skips other lines without a warning). The live path already accepts NIL and maps it to an empty delimiter (providers/live_imap.py), which can serve as the model for the fix.

Owner: Ownmail IC2. Reserved for TASK-16. Review base: da018d5d1dd309ee5767ac8483fc746d7ff3155f. Planned branch: fix/imap-nil-delimiter.
Intended write scope: ownmail/providers/imap.py, limited to parse_list_response; tests/test_imap_provider.py; this task file. Consume ownmail/providers/live_imap.py, ownmail/roles.py and existing role tests read-only. IC1 owns TASK-116's help template, database actual-search regressions and help-route-only test_web assertions. README and the integration checkout are reserved for integration coordination.
The current parser returns no folders for valid synthetic NIL listings. The live parser already maps NIL to an empty delimiter, and role_for_imap_folder already matches the whole name for that delimiter. This bounded change restores the archive parser's missing valid-input route; no new parser framework or role policy is needed. The description's optional malformed-line warning is deferred and is not an acceptance requirement; retain existing best-effort handling of truly malformed lines.
Start from the common committed claim base after both task claims. Use an isolated local worktree in the IC's own writable workspace. Integrate TASK-116 before TASK-16; serialize full suites, browser validation and commit hooks through the coordinator. Preserve every other task and implementation scope.
Validation begins with pytest tests/test_imap_provider.py tests/test_roles.py. Complete the repository's full coverage and required-browser pre-push gate before closure; prove the NIL regression fails against the old parser. Do not exercise a real account or change credentials/OAuth, schema, dependencies, live lifecycle behavior, mail files or publication settings.
Next action: IC2 rechecks the valid-NIL premise and existing parser/role contracts on the common claim base, then confirms or updates this bounded plan before implementation.

IC2 rechecked the claim and confirmed the implementation plan on common base 705aa580b8c0b14905471942918834115329d533. Source inspection confirms the archive regex requires a quoted delimiter while the existing live parser maps NIL to an empty delimiter and role matching already treats that as a flat namespace. Keep the claim review base da018d5d1dd309ee5767ac8483fc746d7ff3155f; the intervening shared commits contain only the two task claims. The assigned quiet window postpones dynamic premise checks, environment preparation and hooks. Next action after release: reproduce the synthetic NIL drop, commit this task-only plan confirmation, then implement and test the minimal parser change.

After the quiet-window release, a synthetic check against the unchanged common-base parser confirmed the premise: quoted Receipts/Sent rows return both original tuples, but the same rows with NIL return no parser tuples and no archive-provider folders. Existing role_for_imap_folder correctly classifies flat Trash and leaves flat Work/Trash unclassified. The missing route is therefore present and worth the bounded fix. No account was connected. Plan confirmed without scope changes; this task-only checkpoint precedes implementation.

Checkpoint-only slot granted. Implementation remains paused while the coordinator checks newly discovered upstream commits for overlap with TASK-16 and TASK-116. Preserve this local plan and common-base worktree; do not independently rebase, merge or push. Next action: resume the bounded implementation only after the coordinator confirms the owned code scope can proceed.

Implementation now accepts NIL alongside the existing quoted delimiter and normalizes its unmatched delimiter group to an empty string. All production code outside parse_list_response is unchanged. The incorrect NIL-as-malformed expectation was replaced because NIL is a valid LIST delimiter; separate malformed-row assertions remain. The new regressions first ran against the original parser: seven positive NIL cases failed while four selected controls passed. After the minimal fix, all 205 provider and role tests passed, including quoted/mixed listings, non-byte and Noselect filtering, whole-name roles, SPECIAL-USE/configured exclusions, discovery and full/incremental mocked scans with watermarks. Ruff check, repository format-check and deptry passed. Author self-review found no introduced issue; shared roles/live parser and README remain untouched. All AC-specific behavior is verified, but the task stays In Progress pending the stable reconciled integration base and assigned full coverage/required-browser/pre-push gate. No real account was contacted.

The coordinator removed the validation-slot prerequisite for isolated worktrees and authorized immediate local full validation and commit hooks. The task runtime uses its own venv, sanitizer node_modules, temporary files, cache and browser profiles; its reusable hook cache belongs only to IC2. Browser tests render private synthetic content, and the local test HTTP server requests an ephemeral port. Proceed with the implementation checkpoint and full required-browser pre-push gate on this branch. Integration/rebase/merge and public push remain coordinator-owned and have not occurred.

Full required validation passed on implementation commit 8a7cf051a8d93e4f83dc2d3183680aaaf07b0139: pre-commit run -a --hook-stage pre-push passed all hooks with mandatory Chromium browser coverage enabled. Pytest reported 3,978 passed and the one pre-existing TASK-13 expected failure; no browser tests were skipped. Aggregate coverage including branches was 96.52%, above the 95% gate. Repository-wide ruff check, ruff format --check and deptry passed. Final author review covered the complete task scope from the recorded review base; an optional read-only Astra Ultra support audit also found no actionable introduced issue. The only production change is parse_list_response. No role policy, live parser, credentials, real mailbox, schema, dependencies or shared README changed. Local implementation is committed and verified; default-branch integration, upstream reconciliation and publication remain coordinated separately.

Authorized audit follow-up from fixed review base 47e54fd653f65a33b394f52207602476dc14126b. The uppercase NIL fix remains useful, but lowercase and mixed-case protocol tokens are still skipped as in the baseline. Add a case-insensitive group for the NIL token only, parameterize existing parser and full/incremental scan cases, prove the new cases fail first, then obtain independent focused review and the combined required gate before restoring Done. Preserve folder-name/flag spelling and role policy. Scope is parse_list_response and existing IMAP tests only. No real server or credential operations.

Audit follow-up implementation: accept ASCII-case variants only inside the NIL token regex group; original folder spelling, flags, delimiters and filtering stay unchanged. Extended existing parser and full/incremental provider tests instead of duplicating them. On unchanged production, nine new mixed-case cases failed and all three uppercase controls passed. With the correction, the combined sanitizer/provider focused run passed 279 tests. Independent focused review and the final combined required gate are pending; keep In Progress.

Accept all ASCII-case variants of the NIL delimiter without changing folder spelling, flags, quoted delimiters or role exclusions. Original and follow-up parser/full/incremental mocked scan regressions pass; nine mixed-case regressions failed before correction. Independent backend review passed 42 tests, 11 subtests and six actual-pipe probes across the full backend correction scope. Final combined verification passed on 6f76b4398d83c6a6217a0e7049428d976e531c63: unchanged pre-commit run -a --hook-stage pre-push, mandatory Chromium enabled, 4163 tests passed in 287.30s, 96.72% aggregate branch-inclusive coverage against 95%. All normal hygiene, Ruff, formatting and deptry checks passed. Exact backend, reader and TASK-125 heads are ancestors; all merged source/test paths were checked against their reviewed contents. No real mail, credential changes or remote operations. The following closure commit changes task metadata only; code and tests remain the verified candidate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accept all ASCII-case variants of the NIL delimiter without changing folder spelling, flags, quoted delimiters or role exclusions. Original and follow-up parser/full/incremental mocked scan regressions pass; nine mixed-case regressions failed before correction. Independent backend review passed 42 tests, 11 subtests and six actual-pipe probes across the full backend correction scope. Combined required gate: 4163 passed, 96.72% coverage; implementation and independent review complete. Local integration is authorized; no public push.
<!-- SECTION:FINAL_SUMMARY:END -->
