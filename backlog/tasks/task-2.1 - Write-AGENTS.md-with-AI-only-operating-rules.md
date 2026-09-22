---
id: TASK-2.1
title: Write AGENTS.md with AI-only operating rules
status: Done
assignee: []
created_date: '2026-07-24 04:42'
updated_date: '2026-09-22 17:25'
labels: []
milestone: m-2
dependencies: []
parent_task_id: TASK-2
priority: medium
ordinal: 5
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create AGENTS.md as the canonical AI-only rules file: autonomy policy (commit at every reasonable checkpoint, never end a turn with a dirty tree, keep the relevant backlog task current — see doc-3), a zero-prompt session-start rule (if the user gives no specific direction at session start, check backlog/ for the next To Do task — lowest ordinal within the earliest open milestone, see doc-4 — and resume work there without waiting to be told or asking which task to do), progress-ledger pointing at backlog/ tasks instead of chat history, code/test/file hygiene guardrails (survey-before-adding, subtractive bias, no dead code, a test must be able to fail, one concern per file), a STOP-and-ask-the-human list scoped to ownmail's real risk areas (DB schema/migrations, credential/keychain handling, OAuth flow, irreversible git ops), and a doc map. Fold in the content currently in .github/copilot-instructions.md rather than duplicating it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 AGENTS.md exists at repo root with the sections above
- [x] #2 .github/copilot-instructions.md content is merged in, not left duplicated
- [x] #3 AGENTS.md documents a zero-prompt session-start rule: no direction given -> check backlog/ for the next To Do task by ordinal/milestone and start on it
- [x] #4 .github/copilot-instructions.md and CLAUDE.md (TASK-2.5) both surface this rule, not just AGENTS.md
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Caveat on the zero-prompt session-start rule: it's straightforward when there's one obvious next task, but needs a tie-breaker once multiple tasks are unblocked at once, or a task was left In Progress by a prior session (resume that before pulling a new To Do one?). Left as an implementation decision - don't over-specify this now, just make sure AGENTS.md's session-start rule accounts for the ambiguity rather than silently assuming only one candidate task ever exists.

**Ledger repair, 2026-09-22 (TASK-42).** Removed number-only accidental criteria and checked the remaining criteria against the current repository.
<!-- SECTION:NOTES:END -->
