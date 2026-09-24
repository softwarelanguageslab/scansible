# CLAUDE.md

This file orients Claude Code sessions working in this repository. It covers architecture and
conventions at a high level so you don't need to re-explore the codebase from scratch each time.
It intentionally omits method/class/file-level detail — read the relevant source for that.

## Project overview

Scansible (CLI: `scansible`) is a static analysis research framework for Ansible
Infrastructure-as-Code, developed as an academic research tool (VUB), not a production linter
product. Four core capabilities:

- **PDG** — a Program Dependence Graph capturing the control flow and data flow of Ansible
  playbooks/roles.
- **AST** — a validated, normalized, typed Abstract Syntax Tree of Ansible code.
- **GASEL** — the Graph-based Ansible SEcurity Linter, a security-smell detector for 7 generic
  security weaknesses.
- **SCA** — Software Composition Analysis, identifying third-party dependencies (collections,
  roles, modules, OS binaries, Python packages) and cross-referencing them against advisories.

## Architecture / pipeline

Conceptual data flow: **YAML → CST → AST → PDG → analysis (checks) and/or SCA reporting.**

- **`cst/`** — Concrete Syntax Tree: parses raw YAML into typed `Yaml*` nodes via a custom,
  Ansible-aware loader so every node keeps its source location. Stays close to the raw file and
  knows nothing about Ansible semantics (task directives, loops, variable precedence) — that's
  the AST's job.
- **`ast/`** — Abstract Syntax Tree, built on the CST: a validated, normalized, immutable,
  Pydantic-typed tree of a role/playbook (tasks, blocks, handlers, variables, directives, role
  metadata, parsed Jinja2 expressions). Normalization is the key responsibility — Ansible allows
  many shorthand/legacy syntaxes for the same construct, and the AST canonicalizes these into one
  shape so the PDG and checks don't each have to special-case Ansible's syntactic variety.
  Extraction (`ast/extractor.py`) can run in a lenient mode tolerating malformed input; node types
  live in `ast/nodes/`.
- **`pdg/`** — Program Dependence Graph, built from the AST: control flow *and* data flow
  (including variable versioning) as a graph backed by `rustworkx`. `pdg/builder/` is organized
  per Ansible construct (playbooks, roles, blocks, task lists, variables, handlers, role
  dependencies) and is the structurally most complex part of the codebase, since building the PDG
  means walking the AST while threading dependencies. `pdg/representation.py` defines the
  graph/node/edge model; `pdg/io/` exports to Graphviz or Neo4j/Cypher. `pdg/canonical.py` (graph
  canonicalization/reduction) is intentionally disabled, not dead code to delete.
- **`checks/`** — runs smell-detection rules over a built PDG. `checks/security/` (GASEL)
  expresses rules as Cypher-like queries against an embedded Kuzu graph database that the PDG is
  loaded into for this purpose. `checks/semantics/` implements general code-quality rules via
  direct AST/PDG traversal instead of graph queries. Both report through a shared
  `Finding`/`RuleBase` model and terminal reporter.
- **`sca/`** — Software Composition Analysis: extracts third-party dependencies (collections,
  roles, modules, Python packages, OS binaries) and cross-references security advisories.
  Dependency extraction relies on an external, separately-built Scala/sbt subproject
  (`DependencyPatternMatcher/` at repo root, built via `sbt assembly`) — the one non-Python part
  of the pipeline, worth knowing before touching SCA code. Reports render to JSON and an HTML
  dashboard (Jinja2 templates in `sca/html/`).
- **`utils/`** — cross-cutting helpers used across the above: project/file path handling, source
  location tracking, collection helpers, Ansible module type-info/knowledge base, misc
  validators.

`console.py` / `__init__.py` define the Click-based CLI entry point (`scansible.cli`).

## CLI commands

- `build-pdg` — parse a project and emit its PDG (Graphviz or Neo4j/Cypher format).
- `check` / `check-all` — run smell detection (security and/or semantic) over a project.
- `sca` — run full Software Composition Analysis: console output + HTML dashboard.
- `extract-dependencies` — SCA subset that dumps extracted dependencies as JSON.
- `bulk-build` — batch variant for processing many projects from an input file.

See `README.md` for full usage examples.

## Key dependencies/tools

`ansible-core` / `ansible` (parsing, collection resolution), `pydantic` v2 (typed AST/Finding
models), `rustworkx` (PDG graph structure), `kuzu` (embedded graph DB for security-rule queries),
`ruamel-yaml` / `pyyaml` (CST parsing), `Jinja2` (expression parsing + HTML report templates),
`graphviz` (PDG export), `click` / `rich` / `loguru` (CLI, console, logging). SCA also depends on
the separate Scala/sbt `DependencyPatternMatcher` subproject, built via `sbt assembly`.

## Dev workflow / tooling

- Package manager: **`uv`** (`uv sync`, `uv run ...`). Build backend: `hatchling`. No
  Makefile/task runner — everything goes through `uv run <tool>`.
- Linting: **`ruff`**, with an extensive `extend-select` rule set. Notably, pydocstyle (`D`) rules
  are intentionally *not* enabled — docstring presence/format is not lint-enforced, matching the
  terse/optional style described below.
- Type checking: **`basedpyright`** in `recommended` mode. Full type hints are expected
  everywhere (enforced by ruff's `ANN` rules + basedpyright). `from __future__ import annotations`
  is mandated project-wide (isort `required-imports`); use PEP 604 union syntax (`X | None`).
- Testing: **`pytest`** + `pytest-describe` (BDD-style nested tests) + `hypothesis`
  (property-based testing, including differential testing against real `ansible` subprocess runs
  for data-flow correctness). No golden-file/snapshot fixtures — expected results are built
  programmatically and compared via custom graph-matcher helpers
  (`tests/helpers/graph_matchers.py`). Tests marked `slow` only run with `--slow`.

## Conventions

**Docstrings** — one short sentence fragment, e.g. `"""Node representing a task."""`. No
`Args:`/`Returns:`/`Parameters` sections, no restating of types already in the signature.
Coverage is partial and selective *by design*: add a docstring only where the name/signature
doesn't already make behavior obvious. It is normal and expected to leave trivial functions,
`__init__`, and simple private helpers undocumented. When more explanation is genuinely needed,
use a one-line summary, a blank line, then 1-2 sentences of rationale — still no param/return
markup. **Err terse**: docstrings written in past sessions have tended to be more verbose/detailed
than this codebase's actual style — match the existing terseness rather than expanding it.

**Comments** — sparse. Explain *why* (rationale, caveats, workarounds, `# TODO:` notes), never
*what* the code already says.

**Commit messages** — Conventional Commits: `type(scope): imperative lowercase description, no
trailing period`. Scope is the module name (`pdg`, `ast`, `checks`, `sca`, `semantics`, ...) and
is omitted for cross-cutting changes. Breaking changes use a `!` suffix, e.g.
`refactor(pdg)!: simplify data flow extraction`.

**Type hints** — full coverage expected throughout, enforced by tooling rather than left to
convention.

## Working with Claude

When revising a plan (in plan mode) in response to user feedback, give a brief in-chat summary of
the feedback received and how the revised plan addresses it, before presenting the updated plan.
