---
id: doc-3
title: AGENTS.md Modernization — meeple survey & doc-structure decision
type: specification
created_date: '2026-07-24 04:42'
---

## Goal

ownmail currently splits AI guidance across `.github/copilot-instructions.md`
(AI-specific) and `CONTRIBUTING.md` (shared human+AI rules), with no
`AGENTS.md` — the emerging cross-tool standard (Codex CLI, Claude Code,
Copilot CLI/cloud agents, Cursor, etc. all look for it). `clee704/meeple`
(same author's other active repo) already built out a mature AGENTS.md /
CONTRIBUTING.md / CLAUDE.md split. This doc records what was surveyed there,
what's being ported, and what's excluded as meeple-specific.

## Doc-structure decision (applies repo-wide)

- **README.md** — overview + usage, for everyone (humans, not AI-specific).
- **CONTRIBUTING.md** — repo rules & conventions for developers, human *and*
  AI alike (commit/PR mechanics, dev setup, testing, migrations).
- **AGENTS.md** — AI-only operating rules (autonomy policy, progress-ledger,
  hygiene guardrails, STOP-and-ask list). Canonical source for AI tooling;
  `CLAUDE.md` and `.github/copilot-instructions.md` become thin pointers into
  it (meeple's `CLAUDE.md` uses an `@AGENTS.md` import for this — same
  pattern, ported here).

## Surveyed from clee704/meeple

`AGENTS.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`.

## Ported / adapted (generic, not meeple-specific)

- Conventional Commits format, type table, scope convention, branch naming
  (`<type>/<short-desc>`), PR title = single-commit header, pre-PR checklist.
- **Progress ledger** concept — meeple uses GitHub issues (`phase`,
  `tech-debt` labels) as the durable, git-adjacent record of in-flight work.
  ownmail already has an equivalent: the `backlog/` task tracker
  (Backlog.md CLI). Ported the *concept* (durable, resumable-from-repo
  progress record) onto the tool ownmail already has, not GitHub issues.
- **Autonomy / "persist proactively" policy** — commit at every reasonable
  checkpoint without waiting to be asked, never end a turn with a dirty
  working tree, keep the backlog task current as work progresses. User
  confirmed adopting this for ownmail (2026-07-24), same as meeple.
- **Engineering guardrails** — code hygiene (survey-before-adding, subtractive
  bias, no dead code/speculative abstractions), test hygiene (a test must be
  able to fail, cover reachable behavior not a percentage, no redundant
  tests), file hygiene (one concern per file, size-as-smell not a hard
  limit). None of this is game-specific; ported near-verbatim.
- **STOP and ask the human when** list — ported and re-scoped to ownmail's
  actual risk areas (schema/migration changes, credential/keychain handling,
  anything touching the OAuth flow, irreversible git ops), dropping the
  meeple entries about game rules/interfaces.
- **Mechanical hygiene tooling** — pre-commit + CI enforcement (ruff, pytest
  + coverage gate) so agents don't have to remember to run checks. deptry
  (unused deps) is plausibly useful for ownmail too; vulture (dead code) and
  import-linter (seam enforcement) are meeple's answer to problems ownmail
  doesn't have at its size (no plugin architecture, no games/framework
  seam) — left out unless a real need shows up.

## Excluded — meeple-specific

- Hard gates G1–G10 (rules-first game onboarding, `framework/`↔`games/` seam,
  solver-compatibility matrix, eval-harness requirement) — all specific to
  meeple's game-engine architecture.
- Per-game onboarding recipe, `RULES.md` template/concept, doc map entries
  for game rules.
- GitHub issue labels `phase` / `tech-debt` as the literal mechanism (kept
  the concept, not the mechanism — see above).
- `import-linter`/`vulture` pre-commit hooks and the frontend build/lint/test
  hooks (ownmail has no comparable frontend build pipeline).
