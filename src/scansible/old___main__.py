from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from textwrap import indent

import click
from loguru import logger
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

from scansible import detector, utils
from scansible.extract import CommitInfo, extract_full_repo, extract_one
from scansible.extractor import extract_structural_graph
from scansible.io import graphml, graphviz, neo4j
from scansible.io.structural_models import import_all_role_heads, parse_role
from scansible.repo_scan import scan_repo_wrap


@click.group()
def group() -> None:
    pass


@group.command()
@click.argument(
    "input", type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True)
)
@click.argument(
    "output", type=click.Path(dir_okay=True, file_okay=False, writable=True)
)
def run_extracted(input: str, output: str) -> None:
    input_path = Path(input)
    output_path = Path(output)
    (output_path / "neo4j").mkdir(exist_ok=True, parents=True)
    (output_path / "graphml").mkdir(exist_ok=True, parents=True)
    (output_path / "dot").mkdir(exist_ok=True, parents=True)

    role_structural_models = import_all_role_heads(input_path)

    for srm in tqdm(role_structural_models):
        # logger.info(srm.role_id)
        sg = extract_structural_graph(srm)
        neo4j_str = neo4j.dump_graph(sg)
        (output_path / "neo4j" / f"{sg.role_name}.txt").write_text(neo4j_str)
        graphml_str = graphml.dump_graph(sg)
        (output_path / "graphml" / f"{sg.role_name}.xml").write_text(graphml_str)
        dot_str = graphviz.dump_graph(sg)
        (output_path / "dot" / f"{sg.role_name}.dot").write_text(dot_str)


@group.command()
@click.argument(
    "input", type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True)
)
@click.argument(
    "output", type=click.Path(dir_okay=True, file_okay=False, writable=True)
)
@click.option("--full/-f", default=False)
def extract(input: str, output: str, full: bool) -> None:
    input_path = Path(input)
    output_path = Path(output)
    (output_path / "neo4j").mkdir(exist_ok=True, parents=True)
    (output_path / "graphml").mkdir(exist_ok=True, parents=True)
    (output_path / "aux").mkdir(exist_ok=True, parents=True)
    (output_path / "dot").mkdir(exist_ok=True, parents=True)
    (output_path / "errors").mkdir(exist_ok=True, parents=True)
    (output_path / "logs").mkdir(exist_ok=True, parents=True)

    with (input_path / "repoPaths_filtered.json").open("r") as f:
        role_paths = json.load(f)

    if full:
        extract_full(role_paths, input_path, output_path)
    else:
        extract_heads(role_paths, input_path, output_path)


def extract_full(
    role_paths: dict[str, Path], input_path: Path, output_path: Path
) -> None:
    (output_path / "status").mkdir(exist_ok=True, parents=True)

    tasks = [
        (role_id, input_path / role_path, output_path)
        for role_id, role_path in role_paths.items()
    ]
    all_success_paths: list[str] = []
    all_commit_infos: dict[str, list[CommitInfo]] = {}
    for result in process_map(
        extract_full_repo, tasks, chunksize=15, desc="Extracting"
    ):
        role_id, success_paths, exceptions, commit_infos = result
        all_success_paths.extend(success_paths)
        if exceptions:
            logger.error(
                f"Failed to extract some graphs for {role_id}: {len(exceptions)} exceptions, first is {exceptions[0]}"
            )
        all_commit_infos[role_id] = commit_infos

    write_commits(all_commit_infos, output_path)
    (output_path / "index.json").write_text(json.dumps(all_success_paths))


def write_commits(commit_infos: dict[str, list[CommitInfo]], output_path: Path) -> None:
    with (output_path / "commits.csv").open("w") as commits_f, (
        output_path / "commit_parents.csv"
    ).open("w") as parents_f:
        commit_writer = csv.writer(commits_f)
        parents_writer = csv.writer(parents_f)
        commit_writer.writerow(["role_id", "commit_sha", "commit_message"])
        parents_writer.writerow(["role_id", "commit_sha", "parent"])
        for role_id, commits in commit_infos.items():
            commit_writer.writerows(
                [role_id, sha, message] for sha, message, _ in commits
            )
            for sha, _, parents in commits:
                parents_writer.writerows(
                    [role_id, sha, parent_sha] for parent_sha in parents
                )


def extract_heads(
    role_paths: dict[str, Path], input_path: Path, output_path: Path
) -> None:
    tasks = [
        (role_id, "HEAD", input_path / role_path)
        for role_id, role_path in role_paths.items()
    ]
    for result in process_map(extract_one, tasks, chunksize=50, desc="Extracting"):
        if len(result) < 6:
            role_id, error = result
            logger.error(f"Failed to extract graph for {role_id}: {error}")
            (output_path / "errors" / f"{role_id}.txt").write_text(str(error))
            continue

        role_id, neo4j_str, graphml_str, dot_str, vis_str, error_str, log_str = result
        if neo4j_str:
            (output_path / "neo4j" / f"{role_id}.txt").write_text(neo4j_str)
            (output_path / "graphml" / f"{role_id}.xml").write_text(graphml_str)
            (output_path / "dot" / f"{role_id}.dot").write_text(dot_str)
            (output_path / "logs" / f"{role_id}.txt").write_text(log_str)
            (output_path / "aux" / f"{role_id}.vis.json").write_text(vis_str)
        if error_str:
            (output_path / "errors" / f"{role_id}.txt").write_text(error_str)


@group.command()
@click.argument(
    "input", type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True)
)
@click.argument(
    "output", type=click.Path(dir_okay=True, file_okay=False, writable=True)
)
def extract_debug(input: str, output: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    input_path = Path(input)
    output_path = Path(output)
    (output_path / "neo4j").mkdir(exist_ok=True, parents=True)
    (output_path / "graphml").mkdir(exist_ok=True, parents=True)
    (output_path / "aux").mkdir(exist_ok=True, parents=True)
    (output_path / "dot").mkdir(exist_ok=True, parents=True)
    (output_path / "errors").mkdir(exist_ok=True, parents=True)

    task = (input_path.name, "HEAD", input_path)
    result = extract_one(task, log_reset=False)
    if len(result) < 6:
        path, error = result
        logger.error(f"Failed to perform extraction for {path}: {error}")
        return

    (role_id, neo4j_str, graphml_str, dot_str, vis_str, error_str, _) = result
    if neo4j_str:
        (output_path / "neo4j" / f"{role_id}.txt").write_text(neo4j_str)
        (output_path / "graphml" / f"{role_id}.xml").write_text(graphml_str)
        (output_path / "dot" / f"{role_id}.dot").write_text(dot_str)
        (output_path / "aux" / f"{role_id}.vis.json").write_text(vis_str)
    if error_str:
        (output_path / "errors" / f"{role_id}.txt").write_text(error_str)


@group.command()
@click.argument(
    "input", type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True)
)
@click.argument(
    "output", type=click.Path(dir_okay=True, file_okay=False, writable=True)
)
def detect(input: str, output: str) -> None:
    input_path = Path(input)
    output_path = Path(output)
    output_path.mkdir(exist_ok=True, parents=True)

    detector.main(input_path, output_path)


@group.command()
@click.argument(
    "source",
    type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True),
)
@click.argument(
    "target",
    type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True),
)
def compare(source: str, target: str) -> None:
    source_path = Path(source)
    target_path = Path(target)

    from tests.helpers.graph_matchers import assert_graphs_match

    for p in tqdm(source_path.iterdir()):
        if not p.is_file() or not p.name.endswith(".xml"):
            continue
        if not (target_path / p.name).is_file():
            tqdm.write("No correspondence found for " + p.name)

        try:
            src_graph = graphml.import_graph(p.read_text())
            target_graph = graphml.import_graph((target_path / p.name).read_text())
            assert_graphs_match(src_graph, target_graph)
        except BaseException as e:
            tqdm.write(p.name + ": " + str(e))


@group.command()
@click.argument("output")
def convert_locations(output: str) -> None:
    warnings_path = Path(output) / "warnings.csv"
    with warnings_path.open("r") as f:
        warnings_it = csv.reader(f)
        warnings = [next(warnings_it)]
        warnings[0].append("warning_file")

        for warning in tqdm(warnings_it):
            warning.append(utils.extract_file_path(warning[-1]))
            warnings.append(warning)

        warnings_out_path = Path(output) / "warnings_with_file_path.csv"
        with warnings_out_path.open("w") as f:
            csv.writer(f).writerows(warnings)


@group.command()
@click.argument(
    "input", type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True)
)
@click.argument(
    "output", type=click.Path(dir_okay=True, file_okay=False, writable=True)
)
def extract_all_locations(input: str, output: str) -> None:
    input_path = Path(input)
    output_path = Path(output)
    output_path.mkdir(exist_ok=True, parents=True)

    tasks = list(detector.create_tasks(input_path))
    with (output_path / "locations.csv").open("wt") as locf:
        writer = csv.writer(locf)
        writer.writerow(["role_name", "commit", "file_path"])
        for result in process_map(
            utils.extract_all_locations,
            tasks,
            chunksize=50,
            desc="Extracting locations",
        ):
            role, commit, locations = result
            writer.writerows((role, commit, loc) for loc in locations)


@group.command()
@click.argument("output")
def extract_variable_names(output: str) -> None:
    warnings_path = Path(output) / "warnings.csv"
    warnings_out_path = Path(output) / "warnings_with_variable_name.csv"
    with warnings_path.open("r") as f, warnings_out_path.open("w") as out_f:
        warnings_reader = csv.reader(f)
        warnings_writer = csv.writer(out_f)

        header = next(warnings_reader)
        header.append("warning_variable_name")
        warnings_writer.writerow(header)

        for warning in tqdm(warnings_reader):
            warning.append(utils.extract_variable_name(warning))
            warnings_writer.writerow(warning)


@group.command()
@click.argument("index")
@click.argument("output")
def scan_commits(index: str, output: str) -> None:
    idx_path = Path(index)
    output_path = Path(output)

    idx = json.loads(idx_path.read_text())
    with (output_path / "warnings.csv").open("r") as warnings_f:
        warnings_reader = csv.reader(warnings_f)
        next(warnings_reader)  # skip header
        role_to_warning_locations = defaultdict(set)
        for name, _, cat, *_, file_name, _ in warnings_reader:
            if cat == "Sanity checks":
                continue
            role_to_warning_locations[name].add(file_name)

    with (output_path / "commit_added_path.csv").open("w") as f_added, (
        output_path / "commit_removed_path.csv"
    ).open("w") as f_removed, (output_path / "commit_renamed_path.csv").open(
        "w"
    ) as f_renamed:
        w_add = csv.writer(f_added)
        w_rename = csv.writer(f_renamed)
        w_remove = csv.writer(f_removed)
        w_add.writerow(["role_id", "commit_sha", "parent_sha", "added_file_path"])
        w_remove.writerow(["role_id", "commit_sha", "parent_sha", "removed_file_path"])
        w_rename.writerow(
            ["role_id", "commit_sha", "parent_sha", "path_before", "path_after"]
        )

        for role_name, role_warning_locations in tqdm(
            role_to_warning_locations.items()
        ):
            role_path = idx_path.parent / idx[role_name]
            added, removed, renamed = utils.find_file_path_changes(
                role_path, role_warning_locations
            )
            w_add.writerows((role_name, *a) for a in added)
            w_remove.writerows((role_name, *r) for r in removed)
            w_rename.writerows((role_name, *r) for r in renamed)


@group.command()
@click.argument("index")
@click.argument("output")
def add_commit_info(index: str, output: str) -> None:
    idx_path = Path(index)
    output_path = Path(output)

    idx = json.loads(idx_path.read_text())
    with (output_path / "commits.csv").open("r") as commits_f:
        commits_reader = csv.reader(commits_f)
        next(commits_reader)  # skip header
        role_to_commits = defaultdict(list)
        for commit in commits_reader:
            role_id, *_ = commit
            role_to_commits[role_id].append(commit)

    with (output_path / "commits_with_date.csv").open("w") as f_date, (
        output_path / "commit_tags.csv"
    ).open("w") as f_tags:
        w_date = csv.writer(f_date)
        w_tags = csv.writer(f_tags)
        w_date.writerow(
            [
                "role_id",
                "commit_sha",
                "commit_message",
                "committed_datetime",
                "committer",
                "author",
            ]
        )
        w_tags.writerow(["role_id", "commit_sha", "tag"])

        for role_id, role_commits in tqdm(role_to_commits.items()):
            role_meta_rel_path = Path("RepositoryMetadata").joinpath(
                *Path(idx[role_id]).parts[1:]
            )
            role_meta_path = idx_path.parent / (
                role_meta_rel_path.with_name(role_meta_rel_path.name + ".yaml")
            )
            ext_commits, role_commit_tags = utils.extract_commit_info(
                role_meta_path, role_commits
            )
            w_date.writerows(ext_commits)
            w_tags.writerows(role_commit_tags)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    group()
