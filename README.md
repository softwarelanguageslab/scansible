# SCAnsible: Static Code Analysis Framework for Ansible

SCAnsible is a static code analysis framework for Ansible including various tools
to perform quality assurance operations for Ansible.

## Core features

- The Ansible Program Dependence Graph (PDG), a graph-based representation capturing
  the control flow and data flow of Ansible playbooks and roles.
- A validated, normalized, and typed Abstract Syntax Tree (AST) of Ansible code.
- GASEL, the Graph-based Ansible SEcurity Linter, a _security smell_ detector
  for Ansible playbooks and roles containing checks for 8 generic security weaknesses.
- Semantic smell detection and general code-quality checks on the PDG.
- A Software Composition Analysis (SCA) which identifies dependencies on third-party
  software in Ansible playbooks, roles, and collections.

## Package overview

The general pipeline consists of: **YAML -> CST -> AST -> PDG -> checks / SCA**.

The Scansible package is laid out as follows:

- `cst/`: Concrete syntax tree (CST) of the raw YAML that preserves the position of each node.
- `ast/`: Typed abstract syntax tree (AST) created from the CST, with validation and normalisation.
- `pdg/`: Program dependence graph (PDG) capturing control and data flow information, exportable to Graphviz or Neo4j.
- `checks/`: Security (GASEL) and semantic smell detection.
- `sca/`: Software composition analysis (SCA) providing a dashboard with dependency information and security advisories.
- `utils/`: Shared helpers.

## Running

Requires Python 3.13 or newer.

1. Install the [`uv`](https://docs.astral.sh/uv/getting-started/installation/) package manager.
2. Install the project and its dependencies: `uv sync`.
3. Uv will have created a _virtual environment_ in `.venv`. Activate it: `source .venv/bin/activate`
4. SCAnsible can now be run using the `scansible` command.
   - For an overview of all commands, run `scansible --help`.
   - For instructions for a single command, run `scansible <command> --help`, e.g., `scansible build-pdg --help`.
5. Optionally, to run the SCA, it is necessary to compile the `DependencyPatternMatcher` project by navigating to the directory and running `sbt assembly`. This should produce a `.jar` file that will be used by the SCA.

If you prefer not to activate the virtual environment manually, it is possible to skip steps 2 and 3 by prefixing all `scansible` commands with `uv run`, e.g., `uv run scansible --help`. This will synchronise the dependencies and activate the environment only for that command.

### Commands

- `build-pdg`: Build the PDG of a project (Neo4j/Cypher or Graphviz output).
- `check`: Run security and/or semantic smell detection on a project.
- `check-all`: Like `check`, but report only findings in one given file, to be used by IDE plugins.
- `sca`: Full SCA with an HTML dashboard.
- `extract-dependencies`: Subset of the SCA that dumps the extracted dependencies as JSON.
- `bulk-build`: Build PDGs for many projects listed in a CSV file.

Global flags `-v`/`-vv` print debug/trace output, and `-q` prints only warnings and errors.
These need to go before the command, e.g., `scansible -v check /path/to/project`.

### Example: Building a PDG and outputting it in Cypher format

```
scansible build-pdg -f neo4j -o neo4j_query.txt /path/to/role-or-playbook
```

### Example: Building a PDG and visualizing it with Graphviz

```
scansible build-pdg -f graphviz -o pdg.dot /path/to/role-or-playbook
dot -Tsvg pdg.dot -o pdg.svg
```

### Example: Controlling project detection and role resolution

The project type (role or playbook) is autodetected, but can be forced with `-t`.
Role dependencies are looked up in the Ansible default paths. Extra directories can be
prepended with `--role-search-path` or the `ROLE_SEARCH_PATH` environment variable
(colon-separated).
By default, malformed tasks are tolerated (`--lenient`). Use `--strict` to abort processing
a file on the first malformed task, and `--errors` to write a summary of build errors to a file.

```
scansible build-pdg -t playbook --strict --errors errors.txt \
    --role-search-path ./vendored-roles /path/to/playbook.yml
```

### Example: Running all smell detection

Security and semantic smell detection are both enabled by default:

```
scansible check /path/to/role-or-playbook
```

To see every rule in action, run it on the showcase playbook, which annotates each task
with the rule it is expected to trigger:

```
scansible check examples/checks_showcase.yml
```

### Example: Running only code smell detection (without security smell detection)

```
scansible check --enable-semantics --skip-security /path/to/role-or-playbook
```

### Example: Running only security smell detection

```
scansible check --enable-security --skip-semantics /path/to/role-or-playbook
```

### Example: Reporting smells for a single file

`check-all` finds all entrypoints (roles and playbooks) in the project and reports
only the findings located in the given file:

```
scansible check-all /path/to/project /path/to/project/roles/web/tasks/main.yml
```

Note that it is still necessary to scan the whole project, as Scansible requires a whole-program analysis.

### Example: Running the SCA

Ensure the `DependencyPatternMatcher` is compiled as described above.
Then, run the SCA:

```
scansible sca /path/to/project /path/to/output
```

This will print information on the project dependencies to the console, and
generate an HTML report in `/path/to/output`.

To run on a concrete example, use the `examples/example.yaml` playbook:

```
scansible sca ./examples/ ./examples_dashboard/
```

This should produce a report containing a hardcoded secret security weakness,
as well as several OS binary and Python package dependencies. One of the Python
packages, `requests`, should contain a number of security advisories.

### Example: Extracting dependencies

This example only extracts dependencies instead of producing an entire SCA report.
As before, ensure `DependencyPatternMatcher` is compiled.
Then, run the tool as follows:

```
scansible extract-dependencies /path/to/project /path/to/output.json
```

This will write all found dependencies (collections, modules, roles, Python packages, and OS binaries) to the output file in JSON format.

Concrete example:

```
scansible extract-dependencies ./examples/ ./example_output.json
```

### Example: Building PDGs in bulk

`bulk-build` reads entrypoints from a CSV file with the columns `repo`, `relative_path`, and `type`
(`role` or `playbook`):

```
repo,relative_path,type
owner/repo,playbooks/site.yml,playbook
owner/other-repo,roles/web,role
```

```
scansible bulk-build entrypoints.csv /path/to/repos /path/to/output
```

Each entrypoint is built separately into `/path/to/output` in Neo4j format. Entrypoints that fail
to build are listed in `failed.csv`, with details in `errors.log`.

## Running tests

This project uses PyTest as the test framework. Tests can be executed as follows:

```
uv run pytest
```

Tests marked `slow` only run when passing `--slow`:

```
uv run pytest --slow
```
