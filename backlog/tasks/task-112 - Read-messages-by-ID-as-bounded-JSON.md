---
id: TASK-112
title: Read messages by ID as bounded JSON
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-24 18:44'
updated_date: '2026-09-30 18:43'
labels: []
dependencies:
  - TASK-111
references:
  - ownmail/cli.py
  - ownmail/archive.py
  - ownmail/parser.py
priority: medium
type: feature
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scripts and assistants need to read a selected search result without writing ad hoc MIME parsers. Add a CLI command that accepts an ID returned by JSON search and returns decoded message content from locally available archive or Active mail. Follow the JSON and read-only behavior established by TASK-111. Attachment content extraction and MCP integration are outside this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An ID from JSON search resolves to the corresponding archived or cached Active message and returns decoded headers, readable text, attachment names, archive/Active status, and a usable original-message reference.
- [x] #2 Returned body text has a documented default and maximum size; callers can select a limit and responses explicitly report truncation.
- [x] #3 Missing IDs, unavailable files, and parse failures return defined errors and nonzero exit status. Stdout remains JSON and diagnostics go to stderr.
- [x] #4 Reading performs no network calls or substantive writes to the index, email files, Active cache, configuration, or credentials, including no initialization, migration, rebuild or implicit creation of application data. It follows the TASK-111 contract: live read-only SQLite handles may perform only normal WAL/SHM coordination-file writes, as explicitly approved by the user.
- [ ] #5 CLI documentation and synthetic-fixture tests cover search-to-read identity, plain-text and HTML-only messages, encoded headers, attachment names, truncation, unavailable content, and absence of writes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pinned review base: clean main 1c7f246fabadd384fed8fc5f4a901bbbb37a26ba; dependency TASK111 is Done. 1. Add ownmail read ID as a JSON-only command, validating --body-limit before opening data (default 20000, maximum 100000 Unicode characters). Reuse TASK111 configuration validation, existing-data acquisition, pinned read-only connections, error envelope and Active status formatting; route ID lookup through the existing connection hook. 2. Resolve an exact search ID to its owned file or verified cached Active payload, preserving dual ownership and incomplete freshness. Use existing archive/cache file boundaries; report missing IDs, unavailable files/state and parse failures distinctly. Include an explicit original local file URI for the selected message; no remote access. 3. Reuse the MIME parser/header/charset/HTML-text/filename helpers with a reader mode that excludes attachment contents, preserves attachment names as a list, and reports actual parse failures without changing indexing defaults. Output body text plus its limit and truncation status; no attachment extraction or MCP. 4. Add synthetic search-to-read, plain/HTML/encoded/attachment/truncation/error and current-WAL/nonmutation checks, plus meaningful failure/mutation controls and retained search/parser tests. Document the command adjacent to JSON search, leaving the concurrent export section untouched. 5. Commit clean checkpoints with normal hooks, obtain independent focused review, then run the mandatory full gate with an exclusive browser lease and reconcile latest main before authorized integration. No real mail, credentials, network service or external push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified: JSON search returns stable IDs, but the CLI has no command to decode a selected result. Existing get_readable_email handles archive/Active resolution; existing parser supplies decoding helpers, and TASK111 provides validated acquisition and formatting. No new runtime dependency or database schema is needed. The task explicitly follows TASK111, so AC4 now states its already-approved coordination-file exception without expanding substantive writes. Output may include a local file URI only for the explicitly selected message, fulfilling the required original-message reference. Shared CLI edits are confined to JSON configuration reuse, the new read command/parser and early dispatch; the existing search response and human default stay compatible. Concurrent PDF/export implementation and its README section remain out of scope. All criteria stay open until evidence and completion gates.

Implementation checkpoint: ownmail read ID now resolves an exact archive or cached Active ID through TASK111 acquisition and the existing get_readable_email path. The ordinary database ID lookup now uses its existing connection hook, so JSON reads stay on the pinned mode=ro handle; normal callers retain sqlite behavior. JSON search/read share configuration validation, ownership/freshness formatting and the error envelope. No export command or export README text changed. Reader MIME mode reuses header/filename/HTML/legacy recovery helpers, excludes attachment subtrees and retains names as list items. A synthetic emoji-only body exposed the existing indexing readability heuristic; reading preserves strictly decoded declared UTF-8 without changing that indexing heuristic, while explicit controls retain Latin-1 conflict recovery, undeclared Korean and declared Cyrillic behavior. Plain text is preferred, empty alternatives fall back to HTML, and parse exceptions produce parse_failed instead of indexing fallback text. Body caps, truncation and original local file URIs are documented. Ten original CLI cases failed before implementation. The latest 36 reader cases pass; 602 combined reader/search/parser/CLI/database/Active checks passed before the final added stdout diagnostic case. Tests exercise actual module search-to-read execution, archive/Active/dual identity and failed-refresh metadata, live archive/Active WAL contents and unchanged substantive bytes, exactly one/two mode=ro handles, unsafe path rejection, no initializer/rebuilder/credentials/network, missing prerequisites, parse errors, interruption, and changed-cache rejection with closed handles. Eight in-memory safety mutations are caught (caps, attachment exclusion, archive boundary, read-only lookup, stdout routing, truncation, declared Unicode and final cache check); the first stdout mutation did not reach its child CLI subprocess, so an in-process diagnostic check was added and caught the mutation. Source files were never mutated for these probes. Full task diff self-review, Ruff and diff checks pass. AC1-4 are evidenced; AC5/task closure remain pending independent focused review and the unchanged mandatory full gate with a browser-only lease. Main remains untouched at the pinned base; no real mail, external service or remote operation occurred.

Independent review found a concrete HTML text loss: the shared pre-existing _strip_html helper used parent.remove(element), which also discarded visible tail text immediately following a hidden style/script/noscript subtree. The new read command exposed that helper bug and could emit an empty body. The bounded correction replaces removal with lxml drop_tree while retaining the identical excluded-element set, so hidden subtree contents remain excluded and visible following text is preserved. No sanitizer, renderer, decoding policy, CLI or acquisition path changed. Five direct parser regressions cover first-child tails, previous siblings, adjacent hidden nodes and noscript; the existing actual subprocess search-to-read test now additionally covers style/script tails while retaining its original plain-text control, timeout, identity, JSON, original-reference and nonmutation assertions. Red evidence: six failures and five passing controls on frozen fccdc5b. Green: 297 parser/reader/search checks passed. Full correction diff self-review and Ruff/format checks passed. Preserve the frozen implementation in ancestry; task remains In Progress for same-reviewer narrow recheck and the single combined PDF/112 full gate owned by the integration coordinator. No browser was launched or other owner state changed.
<!-- SECTION:NOTES:END -->
