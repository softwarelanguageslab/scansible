# SCAnsible: Static Code Analysis Framework for Ansible

SCAnsible is a static code analysis framework for Ansible including various tools
to perform quality assurance operations for Ansible.

## Core features

- The Ansible Program Dependence Graph (PDG), a graph-based representation capturing
  the control flow and data flow of Ansible playbooks and roles.
- The Ansible “structural model”, an Abstract Syntax Tree (AST) of Ansible code.
- GASEL, the Graph-based Ansible SEcurity Linter, a _security smell_ detector
  for Ansible playbooks and roles containing checks for 7 generic security weaknesses.
- A Software Composition Analysis (SCA) which identifies dependencies on third-party
  software in Ansible playbooks, roles, and collections.

## Running

1. Install the [`uv`](https://docs.astral.sh/uv/getting-started/installation/) package manager.
2. Install the project and its dependencies: `uv sync`.
3. Uv will have created a _virtual environment_ in `.venv`. Activate it: `source .venv/bin/activate`
4. SCAnsible can now be run using the `scansible` command.
   - For an overview of all commands, run `scansible --help`.
   - For instructions for a single command, run `scansible <command> --help`, e.g., `scansible build-pdg --help`.
5. Optionally, to run the SCA, it is necessary to compile the `DependencyPatternMatcher` project by navigating to the directory and running `sbt assembly`. This should produce a `.jar` file that will be used by the SCA.

If you prefer not to activate the virtual environment manually, it is possible to skip steps 2 and 3 by prefixing all `scansible` commands with `uv run`, e.g., `uv run scansible --help`. This will synchronise the dependencies and activate the environment only for that command.

### Example: Building a PDG and outputting it in Cypher format.

```
scansible build-pdg -f neo4j -o neo4j_query.txt /path/to/role-or-playbook
```

### Example: Running code smell detection (without security smell detection)

```
scansible check --enable-semantics --skip-security /path/to/role-or-playbook
```

### Example: Running security smell detection

Make sure you have a Redis database running and accessible on port 6379.
The easiest way to do this is by running it as a Docker container:

```
docker run -d --name redis -p 6379:6379 redislabs/redisgraph:2.10.4
```

Then, run Scansible:

```
scansible check --enable-security /path/to/role-or-playbook
```

### Example: Running the SCA

Ensure the `DependencyPatternMatcher` is compiled as described above.
Also ensure that the Redis database is online, as described in the previous point.
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
scansible sca ./examples/ ./example_output.json
```

## Running tests

Ensure that the Redis database is up (see above), then run PyTest:

```
pytest
```
