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

  **TASK-14 was split into three subtasks on 2026-07-25**, and the phase grew
  four neighbours. The full order is below.
- **Ongoing — no fixed slot** (TASK-3): coverage push, independent of the
  phases, no urgency.

## Phase 5 order (settled 2026-07-31)

Work these one at a time, in this order. **This table is the authority.**
Each task's `ordinal` matches it, but neither `backlog task list --plain`
(sorts by priority) nor `backlog board` renders that order, so read it here
rather than trying to recover it from the CLI.

| # | Task | STOP? | Why here |
|---|------|-------|----------|
| 1 | TASK-17 | no | Gmail history watermark race. Loses mail today, and 14.3 makes incremental sync the *only* capture path — fix it while the two failure modes are still separable |
| 2 | TASK-18 | no | `includeSpamTrash` + the drafts exclusion mechanism. Cheap, same file, done first so the filter is built over one exclusion mechanism |
| 3 | TASK-14.3 | no | Eligibility-driven capture. The large half, and the precondition for any filter — without it a filter turns a working archive into one with silent holes |
| 4 | TASK-14.1 | no | The download filter config surface. The small half that was originally mistaken for the whole |
| 5 | TASK-25 | no | Reconcile: sweep the *existing* archive against the filter |
| 6 | TASK-14.2 | **yes** | Purge. Deletes user email, widens the OAuth scope — sign-off, then PR |
| 7 | TASK-33 | no | Whether purge defers for threads still live in the inbox. Evidence-gated: decide after purge has actually run |

### Why this order

**Steps 1–5 are the minimum set to get an existing archive into good shape.**
That was the driving question on 2026-07-31: an archive holding server-side
inbox and trash mail. Steps 1–4 stop it getting worse; step 5 cleans up what
is already on disk. Purge is not part of that — it serves the separate goal
of leaving no mail on third-party servers.

**Reconcile before purge (5 before 6), and this matters.** TASK-25 depends
only on TASK-14.1, so it *can* run before purge, and it *should*: reconcile
moves wrongly-archived mail to ownmail's bin, which un-verifies its local
copy, which takes it out of purge's sweep set. Run purge first and it trashes
the server copies of mail reconcile is about to bin — recoverable from both
bins, but pointlessly so.

**Two sequencing claims were corrected on 2026-07-31:**

- TASK-25 declared no dependencies while its AC #2 requires reading the
  exclusion set from config, which does not exist until TASK-14.1. It could
  not have run first. Dependency added.
- TASK-18 claimed to block TASK-14.1 because one of the filter's values was
  unreachable. That reason died when TASK-14.1 fixed trash and spam as
  permanently excluded on 2026-07-26 — nothing will ever need
  `includeSpamTrash=True`. It stays at position 2 as tidy-up, not as a gate;
  if it slips behind TASK-14.1, nothing breaks. See its Implementation Notes.

### Not in this phase

TASK-28 (active messages) depends on TASK-14.3 but is a pure addition — a
read-only window onto the pre-capture set. It is not required for the archive
to be correct, and it is deliberately left unscheduled.

## Keeping this current

If a task's priority, scope, or dependencies change materially, update its
`milestone`/`ordinal` (via `backlog task edit <id> -m <milestone> --ordinal
<n>`) and amend this doc's rationale — don't let the two drift apart.
