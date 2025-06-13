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

1. Install the [Poetry](https://python-poetry.org/) package manager
2. Install the project and its dependencies: `poetry install` (in the project directory)
3. Activate the Poetry shell to activate the virtualenv: `poetry shell`.
   Alternatively, you can opt not to activate the shell, but then you need to prefix every subsequent Python command with `poetry run`.
   E.g., `python -m scansible --help` becomes `poetry run python -m scansible --help`
4. Scansible can now be run as `python -m scansible`.
   For an overview of all commands, run `python -m scansible --help`.
   For instructions on a single command, run `python -m scansible <command> --help`, e.g., `python -m scansible build-pdg --help`.
5. Optionally, if running the SCA, it is necessary to compile the `DependencyPatternMatcher` project by navigating to the directory and running `sbt assembly`. This should produce a `.jar` file that will be used by the SCA.

### Example: Building a PDG and outputting it in Cypher format.

```
python -m scansible build-pdg -f neo4j -o neo4j_query.txt /path/to/role-or-playbook
```

### Example: Running code smell detection (without security smell detection)

```
python -m scansible check --enable-semantics --skip-security /path/to/role-or-playbook
```

### Example: Running security smell detection

Make sure you have a Redis database running and accessible on port 6379.
The easiest way to do this is by running it as a Docker container:

```
docker run -d --name redis -p 6379:6379 redislabs/redisgraph:2.10.4
```

Then, run Scansible:

```
python -m scansible check --enable-security /path/to/role-or-playbook
```

### Example: Running the SCA

Ensure the `DependencyPatternMatcher` is compiled as described above.
Also ensure that the Redis database is online, as described in the previous point.
Then, run the SCA:

```
python -m scansible sca /path/to/project /path/to/output
```

This will print information on the project dependencies to the console, and
generate an HTML report in `/path/to/output`.

To run on a concrete example, use the `examples/example.yaml` playbook:

```
python -m scansible sca examples/ /path/to/output
```

This should produce a report containing a hardcoded secret security weakness,
as well as several OS binary and Python package dependencies. One of the Python
packages, `requests`, should contain a number of security advisories.

## Running tests

Ensure that the Redis database is up (see above), then run PyTest:

```
pytest
```
