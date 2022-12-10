import re
import git
import yaml
from pathlib import Path
from collections import defaultdict

from .io import graphml

def extract_file_path(loc: str) -> str:
    if loc == 'tasks/main.yml':
        return loc

    if loc.endswith('via initial role load'):
        return loc.removesuffix('via initial role load').strip()

    if loc.startswith('/private/var/folders/'):
        assert len(loc.split('/')) > 8, f'Weird location: {loc}'
        loc = '/'.join(loc.split('/')[8:])

    if loc.startswith('/var/folders/'):
        assert len(loc.split('/')) > 7, f'Weird location: {loc}'
        loc = '/'.join(loc.split('/')[7:])

    if ' via /private/var/folders/' in loc or ' via /var/folders/' in loc:
        loc = re.sub(r' via (?:/private)?/var/folders/.+$', '', loc)

    # Remove line and column number
    loc = re.sub(r':\d+:\d+$', '', loc)

    if not loc.startswith(('tasks/', 'vars/', 'defaults/', 'includes/')):
        print(f'Weird location: {loc}')

    assert loc.lower().endswith(('.yml', '.yaml')), f'Weird location: {loc}'
    assert ' via ' not in loc, f'Weird location: {loc}'

    return loc


def extract_variable_name(warning: list[str]) -> str:
    _, _, cat, rule, _, title, *_ = warning
    if cat == 'Sanity checks':
        return ''

    if rule == 'Unconditional override':
        mtch = re.match(r'Potential unintended unconditional override of variable "([^@]+)@\d+"', title)
        assert mtch is not None, title
        return mtch.group(1)

    if rule == 'Unused because shadowed':
        mtch = re.match(r'Unused variable "([^@]+)@\d+" because it is already defined', title)
        assert mtch is not None, title
        return mtch.group(1)

    if cat == 'Unnecessarily high precedence':
        mtch = re.match(r'Unnecessary use of (?:set_fact|include_vars) for variable "([^@]+)@\d+"', title)
        if mtch is None:
            print(title)
            assert '{{' in title
            return ''
        return mtch.group(1)

    if cat == 'Unsafe reuse':
        mtch = re.match(r'Potentially unsafe reuse of variable "([^@]+)@\d+" due to', title)
        assert mtch is not None, title
        return mtch.group(1)

    raise ValueError(f'Unsupported rule: {cat}::{rule} "{title}"')


AddedFiles = list[tuple[str, str, str]]
DeletedFiles = list[tuple[str, str, str]]
RenamedFiles = list[tuple[str, str, str, str]]

def find_file_path_changes(role_path: Path, paths: set[str]) -> tuple[AddedFiles, DeletedFiles, RenamedFiles]:
    repo = git.Repo(role_path)
    commit_it = repo.iter_commits(paths=list(paths))
    adds, deletes, renames = [], [], []
    for commit in commit_it:
        commit_sha = commit.hexsha
        for parent in (commit.parents or [git.NULL_TREE]):
            parent_sha = '' if parent is git.NULL_TREE else parent.hexsha
            for diff in commit.diff(parent, paths=list(paths), R=parent is not git.NULL_TREE):
                if diff.change_type == 'A':
                    adds.append((commit_sha, parent_sha, diff.b_path))
                elif diff.change_type == 'D':
                    deletes.append((commit_sha, parent_sha, diff.a_path))
                elif diff.change_type == 'R':
                    renames.append((commit_sha, parent_sha, diff.a_path, diff.b_path))

    return adds, deletes, renames

ExtCommit = tuple[str, str, str, str, str, str]  # role_id, commit_sha, commit_msg, committed_datetime, committer, author
CommitTag = tuple[str, str, str]  # role_id, commit_sha, tag

def extract_commit_info(role_meta_path: Path, prev_commits: list[tuple[str, str, str]]) -> tuple[list[ExtCommit], list[CommitTag]]:
    meta = yaml.load(role_meta_path.read_text(), Loader=yaml.CLoader)
    commit_to_meta = {c['sha1']: c for c in meta['commits']}
    commit_to_meta['HEAD'] = meta['commits'][0]
    commit_to_tags: dict[str, set[str]] = defaultdict(set)
    for tag in meta['tags']:
        commit_to_tags[tag['commit_sha1']].add(tag['name'])

    ext_commits: list[ExtCommit] = []
    commit_tags: list[CommitTag] = []
    for c in prev_commits:
        try:
            cmeta = commit_to_meta[c[1]]
        except KeyError:
            ext_commits.append((*c, '', '', ''))
            continue
        ext_commits.append((*c, cmeta['committed_datetime'], cmeta['committer_name'], cmeta['author_name']))
        commit_tags.extend((c[0], c[1], tname) for tname in commit_to_tags[c[1]])

    return ext_commits, commit_tags

def extract_all_locations(args: tuple[Path, Path, str, str]) -> tuple[str, str, list[str]]:
    graphml_path, _, role_id, role_version = args
    try:
        graph = graphml.import_graph(graphml_path.read_text(), role_id, role_version)
        locs = {extract_file_path(n.location) for n in graph if hasattr(n, 'location') and n.location != 'external file'}

        return graph.role_name, graph.role_version, list(locs)
    except Exception as err:
        print(f'{graphml_path}: {type(err).__name__}: {err}')
        # logger.exception(err)
        return role_id, role_version, []
