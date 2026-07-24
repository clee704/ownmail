---
id: TASK-12
title: Global --verbose is dropped when placed before the subcommand
status: To Do
assignee: []
created_date: '2026-07-24 20:55'
labels: []
dependencies: []
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`ownmail --verbose verify` runs with verbose=False; `ownmail verify --verbose` works.

_add_global_opts() in ownmail/cli.py adds a second -v/--verbose (store_true, default False) to every subparser so the flag works 'in any position'. Because both use dest='verbose' and share one namespace, the subparser parse runs second and overwrites the global True with its own False default. The helper defeats the thing it exists to enable.

Same defect applies to any other option added by _add_global_opts.

Fix candidates: give the subparser copies default=argparse.SUPPRESS, or a distinct dest that is OR-ed with the global value.

Found while writing CLI tests for TASK-3; a test asserting the pre-subcommand form is left out until this is fixed.
<!-- SECTION:DESCRIPTION:END -->
