---
id: TASK-16
title: IMAP folders with a NIL hierarchy delimiter are silently dropped
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-07-25 05:24'
updated_date: '2026-09-30 06:07'
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
- [ ] #1 Valid LIST rows with a NIL hierarchy delimiter produce the original folder name and flags with an empty delimiter; quoted-delimiter rows and mixed quoted/NIL listings retain their existing results.
- [ ] #2 Non-byte entries, genuinely malformed rows and nonselectable folders retain the existing skip behavior; a valid NIL row is no longer classified as malformed.
- [ ] #3 NIL folders use whole-name role matching and existing SPECIAL-USE, configured-folder and role-exclusion rules without changing those policies.
- [ ] #4 Synthetic parser and mocked-provider regressions show eligible NIL folders reach archive listing/scanning and role discovery while excluded folders remain excluded; the valid-NIL regression fails against the original parser, with existing quoted-delimiter coverage preserved.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Independently reconfirm the valid-NIL drop with synthetic LIST responses and inspect parse_list_response, the existing live parser, role matching and provider regression helpers.
2. Change only the archive LIST parser to accept NIL and return an empty delimiter, preserving quoted delimiters, names/flags and existing filtering. Reuse established conventions without refactoring the separate strict live lifecycle parser or changing role policy.
3. Replace the existing NIL-as-unparseable assertion with valid-NIL coverage and retain a genuinely malformed-input regression. Cover mixed listings, non-byte entries, nonselectable folders, flat whole-name role matching, configured exclusions, role discovery and eligible NIL folders reaching mocked archive scans.
4. Run focused provider/role tests, then the repository's complete coverage/browser/pre-push gate in the assigned validation slot; self-review the full task diff, record results, and close this task with normal hooks.
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
<!-- SECTION:NOTES:END -->
