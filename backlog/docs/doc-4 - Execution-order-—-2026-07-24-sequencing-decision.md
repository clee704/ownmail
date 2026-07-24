---
id: doc-4
title: Execution order — 2026-07-24 sequencing decision
type: specification
created_date: '2026-07-24 05:10'
---

## Goal

TASK-2 through TASK-7 were all filed in one session with no fixed sequencing
beyond a few explicit `dependencies:` links. This doc records the reasoning
behind the order, tracked mechanically via each task's `milestone` and
`ordinal` fields (`backlog task list` / `backlog board` reflect it directly;
`ordinal` gives the exact linear sequence within and across milestones).

## Ordering principles, in priority order

1. **Hard dependencies win.** A task's `dependencies:` field is a real
   constraint, not a suggestion (e.g. TASK-2.6 needs TASK-4 first; TASK-3
   needs TASK-2.6; TASK-6.2 needs TASK-6.1).
2. **Fix correctness before building UI on top of it.** TASK-5.2/5.3 (Trash
   sync bug, missing read/unread state) land before TASK-5.1 (label sidebar)
   — no point surfacing a label sidebar or unread badges on top of data
   that's wrong or missing.
3. **Cheap + independently valuable work goes first.** TASK-4 (version bump)
   and TASK-7 (import) have zero dependencies and don't block on anything
   else landing — no reason to sequence them behind the docs/process work.
4. **Lock in process/CI guardrails before more feature work accumulates.**
   AGENTS.md, CONTRIBUTING.md, and CI (TASK-2.1/2.2/2.6) come before the
   bigger UI pushes (Phase 4), so that and everything after it is built
   under the new conventions rather than retrofitted later.
5. **Large, independent slogs are not gates.** TASK-3 (95% coverage) only
   has one hard dependency (TASK-2.6) and doesn't block anything else — it's
   parked in its own "Ongoing" milestone rather than a numbered phase, to be
   chipped away at whenever, rather than treated as a blocking step.

## Phases (milestones)

- **Phase 1 — Quick wins & unblocking** (TASK-4, TASK-7): trivial and/or
  high-value work with no dependencies.
- **Phase 2 — Correctness fixes** (TASK-5.2, TASK-5.3): real data bugs,
  both touch `imap.py` — sequenced back-to-back to avoid merge conflicts
  rather than done in parallel.
- **Phase 3 — Process & hygiene** (TASK-2.1, 2.2, 2.6, 2.5, 2.3, 2.4):
  AGENTS.md/CONTRIBUTING.md first, then CI (needs TASK-4 done), then the
  CLAUDE.md/copilot pointer, then ROADMAP.md retirement and README trim.
- **Phase 4 — UI features** (TASK-5.1, TASK-6.1, TASK-6.2): label sidebar,
  then thread grouping, then the threaded list view.
- **Phase 5 — Remote drain** (TASK-14): added 2026-07-24 after the stack
  architecture was settled in doc-6. TASK-14 (optional purge + configurable
  download filter) is the only net-new capability that decision produced.
  TASK-15 was filed alongside it and then closed — the two-knob design
  turned it into a config value rather than a code decision.

  **TASK-14 depends on TASK-5.2, so Phase 5 follows Phase 2.** An earlier
  version of this doc said otherwise, on the grounds that INBOX is already
  standardized across providers. That claim was wrong even for INBOX — see
  doc-6 for why. Canonical system-label mapping is a correctness
  precondition for purge: a label that fails to resolve means messages get
  purged that shouldn't be.

  TASK-14 is a STOP item on two counts — it deletes user email and changes
  OAuth scopes — so it needs sign-off and lands via PR.
- **Ongoing — no fixed slot** (TASK-3): coverage push, independent of the
  phases, no urgency.

## Keeping this current

If a task's priority, scope, or dependencies change materially, update its
`milestone`/`ordinal` (via `backlog task edit <id> -m <milestone> --ordinal
<n>`) and amend this doc's rationale — don't let the two drift apart.
