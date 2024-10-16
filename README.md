# Scansible: Static Code Analysis Framework for Ansible

// TODO: Write better README.

## Running
1. Install the [Poetry](https://python-poetry.org/) package manager
2. Install the project and its dependencies: `poetry install` (in the project directory)
3. Activate the Poetry shell to activate the virtualenv: `poetry shell`.
   Alternatively, you can opt not to activate the shell, but then you need to prefix every subsequent Python command with `poetry run`.
   E.g., `python -m scansible --help` becomes `poetry run python -m scansible --help`
4. Scansible can now be run as `python -m scansible`.
   For an overview of all commands, run `python -m scansible --help`.
   For instructions on a single command, run `python -m scansible <command> --help`, e.g., `python -m scansible build-pdg --help`.

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

## Running tests
Ensure that the Redis database is up (see above), then run PyTest:
```
pytest
```
