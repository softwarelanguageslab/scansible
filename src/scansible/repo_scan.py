from __future__ import annotations

from typing import Iterable

import csv
import json
from collections import defaultdict
from pathlib import Path

from git import Repo

AddedFiles = list[str]
RenamedFiles = list[tuple[str, str]]  # from, to


def get_commit_diffs(c1: Commit, c2: Commit) -> tuple[AddedFiles, RenamedFiles]:
    """c1 = after, c2 = before"""
    d = c2.diff(c1)
    added: AddedFiles = []
    renamed: RenamedFiles = []
    for add in d.iter_change_type("A"):
        added.append(add.b_path)
    for rename in d.iter_change_type("R"):
        renamed.append((rename.rename_from, rename.rename_to))

    return added, renamed


def scan_repo(
    p: Path, cs: list[tuple[str, str]], name: str
) -> Iterable[tuple[str, str, str, AddedFiles, RenamedFiles]]:
    r = Repo(p)
    for c_sha, parent_sha in cs:
        c1 = r.commit(c_sha)
        c2 = r.commit(parent_sha)
        added, renamed = get_commit_diffs(c1, c2)
        yield (name, c_sha, parent_sha, added, renamed)


def scan_repo_wrap(args):
    return list(scan_repo(*args))
