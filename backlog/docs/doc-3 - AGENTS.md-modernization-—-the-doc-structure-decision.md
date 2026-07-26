---
id: doc-3
title: AGENTS.md modernization — the doc-structure decision
type: specification
created_date: '2026-07-24 04:42'
---

## Goal

ownmail split its AI guidance across `.github/copilot-instructions.md`
(AI-specific) and `CONTRIBUTING.md` (shared human+AI rules), with no
`AGENTS.md` — the emerging cross-tool standard that Codex CLI, Claude Code,
Copilot CLI and cloud agents, Cursor and others all look for. This doc
records the structure adopted instead, and what was deliberately left out.

The conventions below were adapted from a mature AGENTS.md /
CONTRIBUTING.md / CLAUDE.md split already running in `clee704/meeple`, a
sibling project by the same author. Files surveyed there: `AGENTS.md`,
`CONTRIBUTING.md`, `CLAUDE.md`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`. That is the last mention of provenance — the
rest of this doc states the decisions on their own terms, because that is
what a future reader needs.

## Doc-structure decision (applies repo-wide)

- **README.md** — overview + usage, for everyone. Not AI-specific.
- **CONTRIBUTING.md** — repo rules and conventions for developers, human
  *and* AI alike: commit/PR mechanics, dev setup, testing, migrations.
- **AGENTS.md** — AI-only operating rules: autonomy policy, progress ledger,
  hygiene guardrails, STOP-and-ask list. The canonical source for AI
  tooling. `CLAUDE.md` and `.github/copilot-instructions.md` become thin
  pointers into it, `CLAUDE.md` via an `@AGENTS.md` import.

The split exists so that one rule lives in exactly one file. A rule that
applies to humans and AI alike belongs in CONTRIBUTING.md and is *not*
restated in AGENTS.md; duplicating it guarantees the two copies diverge.

## Adopted

- **Commit and branch conventions** — Conventional Commits with a type
  table and scope convention, branch naming `<type>/<short-desc>`, PR title
  equal to the single-commit header, and a pre-PR checklist.

- **A progress ledger.** The durable, resumable-from-repo record of
  in-flight work, on the principle that chat history disappears and the
  repo does not. ownmail already had the right tool for it — the `backlog/`
  task tracker (Backlog.md CLI) — so the concept was adopted onto that
  rather than onto GitHub issues, which is what the surveyed repo uses.

- **Autonomy policy.** Commit at every reasonable checkpoint without
  waiting to be asked; never end a turn with a dirty working tree; keep the
  backlog task current as work progresses rather than at the end. Confirmed
  for ownmail 2026-07-24.

- **Engineering guardrails.** Code hygiene (survey before adding,
  subtractive bias, no dead code or speculative abstractions), test hygiene
  (a test must be able to fail, cover reachable behaviour rather than a
  percentage, no redundant tests), file hygiene (one concern per file, size
  as a smell rather than a hard limit).

- **A STOP-and-ask list**, scoped to ownmail's own risk areas: schema and
  migration changes, credential and keychain handling, anything touching the
  OAuth flow, irreversible git operations.

- **Mechanical hygiene tooling** — pre-commit plus CI enforcement of ruff
  and pytest with a coverage gate, so agents don't have to remember to run
  checks. deptry (unused dependencies) earns its place given invariant #4,
  minimal dependencies.

## Left out

- **Architectural hard gates** — the surveyed repo enforces a set of gates
  around its game-engine seams (a `framework/`↔`games/` boundary, a
  solver-compatibility matrix, an eval-harness requirement, a rules-first
  onboarding recipe). They are answers to a plugin architecture ownmail does
  not have. Nothing here transfers.

- **vulture (dead code) and import-linter (seam enforcement).** Both address
  problems of scale and layering that ownmail doesn't have at its size.
  Excluded unless a real need shows up — adding a hook that never fires
  trains people to ignore hook output.

- **Frontend build/lint/test hooks.** ownmail has no comparable build
  pipeline.
