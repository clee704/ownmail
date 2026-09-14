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

## Phase 5 order (updated 2026-09-14)

Work these one at a time, in this order among eligible tasks. **This table is the authority.**
Each task's `ordinal` matches it, but neither `backlog task list --plain`
(sorts by priority) nor `backlog board` renders that order, so read it here
rather than trying to recover it from the CLI.

| # | Task | STOP? | Why here |
|---|------|-------|----------|
| 1 | ~~TASK-17~~ | no | **Done.** Gmail history watermark race. Loses mail today, and 14.3 makes incremental sync the *only* capture path — fix it while the two failure modes are still separable |
| 2 | ~~TASK-18~~ | no | **Done.** `includeSpamTrash`. Cheap, same file, done first so the filter is built over one exclusion mechanism. The drafts mechanism it was also carrying went back to TASK-14.1 — see below |
| 3 | ~~TASK-14.3~~ | no | **Done.** Reconsider messages that become eligible after arrival |
| 4 | ~~TASK-14.1~~ | no | **Done.** Configure capture filters using canonical roles |
| 5 | ~~TASK-25~~ | no | **Done.** Reconcile existing archived mail against the filter |
| 6 | TASK-90 | no | Keep required label lookup failures retryable before finalizing capture |
| 7 | TASK-28 | if schema changes | Add Active reading and search, preserve existing archives, and define compatibility for old capture settings |
| 8 | TASK-38 | no | Protect live threads from server cleanup without delaying capture |
| 9 | TASK-14.2 | **yes** | Verify complete owned copies and server identity before moving inactive server copies to Trash |
| 10 | ~~TASK-33~~ | no | **Done as a historical decision record.** Capture deferral is superseded by the ownership philosophy and revised TASK-38 |

[Mail ownership (TASK-14)](<../tasks/task-14 - Drain-remote-servers-—-delete-archived-mail-once-verified-locally.md#resume>)
defines the bounded workstream and continuation rule. For that workstream,
resume an eligible member already in progress; otherwise select the first
eligible unfinished member in this table. A pending approval or other recorded
blocker may be skipped without waiving it: TASK-38 may proceed while TASK-28
waits because it has no dependency on TASK-28. If this path has no eligible
member, select the independent TASK-5.4. After the path finishes, TASK-5.4 must
also finish before the workstream is complete. Its earlier milestone does not
move it ahead of the main path for a workstream continuation.

### Why this order

**Steps 1–5 addressed the archive problems identified on 2026-07-31:** an archive holding server-side
inbox and trash mail. Steps 1–4 stop it getting worse; step 5 cleans up what
is already on disk. Purge is not part of that — it serves the separate goal
of leaving no mail on third-party servers.

**Reconcile before purge (5 before 9), and this matters.** TASK-25 depends
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

**Scope moved on 2026-07-31, when TASK-18 landed.** The drafts exclusion
mechanism went with it, back to TASK-14.1. `includeSpamTrash` is all-or-nothing
over trash and spam and reaches no other role, so drafts need a mechanism of
their own — but building one in TASK-18 would have meant either adding DRAFTS
to the excluded role set, which is shared with `imap.py` and so is the
default-behaviour change doc-6 attributes to TASK-14, or shipping a role
nothing selects. TASK-18 stayed what its row says: one visible mechanism per
path, nothing decorative on top. Phase 5's order is unaffected.

**Updated 2026-09-14:** [Ownership philosophy](../../docs/philosophy.md)
separates Active downloads, archive capture, and server cleanup. TASK-38 now
protects live threads from cleanup while eligible messages archive immediately.
TASK-89's coverage audit adds TASK-90 for the existing label-failure capture
gap, then schedules TASK-28 before thread protection and cleanup. TASK-28 needs
the capture fix; TASK-14.2 depends on TASK-90, TASK-38, and TASK-28 so its
integration checks exercise the complete lifecycle. Active viewing and
thread protection share provider state rules, but neither needs the other's UI
to exist. Their listed order is a delivery choice, not a hard dependency.

The old evidence gate and capture deferral described below are historical.

**Historical changes on 2026-08-06**, after the user's question about what the
clean split actually needs:

- **TASK-33 closed as a decision record**, and TASK-38 was filed to carry the
  build. Its AC required deciding *after* purge had run; the shape was settled
  ahead of that instead, deliberately. What the evidence gate was protecting
  against — committing to a mechanism nobody needs — survives on TASK-38,
  which is still gated on the gap being observed. What changed is that the
  observation no longer has to wait for purge: capture-without-purge already
  produces incomplete threads inside ownmail, which is enough to judge by.
  The decision also **reversed TASK-33's own placement** of the rule, moving
  it from purge to capture. See that task for why.
- **TASK-38 sits at 6, before purge**, because thread deferral changes what
  gets captured, and purge only ever acts on captured mail. Building it after
  purge would mean purging server copies of exactly the mid-conversation mail
  the rule exists to hold back.

### Independent work

TASK-5.4 supplies local archive label editing and can proceed independently of
Active viewing and cleanup. Its existing milestone and ordinal are unchanged.
TASK-36's optional provenance investigation is not a dependency: captured labels
are owned locally regardless of their origin.

TASK-28 now has a delivery slot. Enablement defaults, refresh cadence, count
semantics, and provider support for unfinished outgoing mail remain decisions
within that task, with documented compatibility and failure behavior required.

## UI redesign (filed 2026-09-12)

TASK-32 now has six subtasks following renewed feedback about the current UI.
This is an unscheduled workstream; the existing milestone order is unchanged.
The ordinals below order this parent's children, not all unmilestoned work.

| Order | Task | Outcome | Hard dependency |
|---|---|---|---|
| 1 | TASK-32.1 | Compare visual directions and apply shared styles to the app shell | None |
| 2 | TASK-32.2 | Responsive sidebar and folder navigation | TASK-32.1 |
| 3 | TASK-32.3 | Clear message rows, search controls and pagination | TASK-32.1 |
| 4 | TASK-32.4 | Readable message detail and return to the originating results | TASK-32.1 |
| 5 | TASK-32.5 | Accessible names, keyboard operation and focus handling | None |
| 6 | TASK-32.6 | Empty states and pending, success and failure feedback | None |

Settle the visual direction first so navigation, lists and reading views use
the same styles. Their listed order reduces shared-template churn; they do
not depend on each other's completion. Accessibility and action feedback can
land independently on the current UI and should retain their behavior through
the redesign.

These tasks do not require conversation grouping, local label editing or
active-message storage. Those remain TASK-6, TASK-5.4 and TASK-28. Label
exclusion, classification and storage repair remain TASK-19, TASK-26 and
TASK-27. UI work preserves the existing distinction between the local bin
and historical server-trash labels described in doc-9.

## Keeping this current

If a task's priority, scope, or dependencies change materially, update its
`milestone`/`ordinal` (via `backlog task edit <id> -m <milestone> --ordinal
<n>`) and amend this doc's rationale — don't let the two drift apart.
