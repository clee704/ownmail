---
id: TASK-4
title: 'Drop Python 3.8/3.9 support, bump minimum to 3.10'
status: To Do
assignee: []
created_date: '2026-07-24 04:51'
updated_date: '2026-07-24 05:10'
labels: []
milestone: m-0
dependencies: []
priority: medium
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Python 3.8 reached EOL 2024-10-07 and 3.9 reached EOL 2025-10-31 - both are past upstream security-patch support already. Bump pyproject.toml's requires-python to >=3.10, drop the 3.8/3.9 classifiers, and update ruff's target-version from py38 to py310 (may surface new lint opportunities - e.g. PEP 604 X | Y unions, match statements - but don't force a rewrite, just let ruff flag what's newly available). No sys.version_info-gated compat code found in ownmail/ to clean up, so this is mostly a metadata + tooling-config change. README/CONTRIBUTING install instructions don't mention a version floor, so no doc update needed there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pyproject.toml requires-python is >=3.10
- [ ] #2 3.8 and 3.9 classifiers removed
- [ ] #3 ruff target-version bumped to py310
<!-- AC:END -->
