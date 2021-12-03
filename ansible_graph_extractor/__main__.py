import json
import sys
from pathlib import Path
from textwrap import indent

import click
from loguru import logger
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

from ansible_graph_extractor.extractor import extract_structural_graph
from ansible_graph_extractor.io import graphml, neo4j, graphviz
from ansible_graph_extractor.io.structural_models import import_all_role_heads, parse_role
from ansible_graph_extractor.extract import extract_one
from ansible_graph_extractor.detector import detect_one_graph
from ansible_graph_extractor.detector.conflicting_variables import ConflictingVariables

@click.group()
def group() -> None:
    pass

@group.command()
@click.argument('input', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
@click.argument('output', type=click.Path(dir_okay=True, file_okay=False, writable=True))
def run_extracted(input: str, output: str) -> None:
    input_path = Path(input)
    output_path = Path(output)
    (output_path / 'neo4j').mkdir(exist_ok=True, parents=True)
    (output_path / 'graphml').mkdir(exist_ok=True, parents=True)
    (output_path / 'dot').mkdir(exist_ok=True, parents=True)

    role_structural_models = import_all_role_heads(input_path)

    for srm in tqdm(role_structural_models):
        # logger.info(srm.role_id)
        sg = extract_structural_graph(srm)
        neo4j_str = neo4j.dump_graph(sg)
        (output_path / 'neo4j' / f'{sg.role_name}.txt').write_text(neo4j_str)
        graphml_str = graphml.dump_graph(sg)
        (output_path / 'graphml' / f'{sg.role_name}.xml').write_text(graphml_str)
        dot_str = graphviz.dump_graph(sg)
        (output_path / 'dot' / f'{sg.role_name}.dot').write_text(dot_str)

@group.command()
@click.argument('input', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
@click.argument('output', type=click.Path(dir_okay=True, file_okay=False, writable=True))
def extract(input: str, output: str) -> None:
    input_path = Path(input)
    output_path = Path(output)
    (output_path / 'neo4j').mkdir(exist_ok=True, parents=True)
    (output_path / 'graphml').mkdir(exist_ok=True, parents=True)
    (output_path / 'dot').mkdir(exist_ok=True, parents=True)
    (output_path / 'errors').mkdir(exist_ok=True, parents=True)
    (output_path / 'logs').mkdir(exist_ok=True, parents=True)

    with (input_path / 'repoPaths.json').open('r') as f:
        role_paths = json.load(f)

    tasks = [(role_id, input_path / role_path) for role_id, role_path in role_paths.items()]
    for result in process_map(extract_one, tasks, chunksize=50, desc='Extracting'):
        if len(result) < 5:
            role_id, error = result
            logger.error(f'Failed to extract graph for {role_id}: {error}')
            (output_path / 'errors' / f'{role_id}.txt').write_text(str(error))
            continue

        role_id, neo4j_str, graphml_str, dot_str, error_str, log_str = result
        if neo4j_str:
            (output_path / 'neo4j' / f'{role_id}.txt').write_text(neo4j_str)
            (output_path / 'graphml' / f'{role_id}.xml').write_text(graphml_str)
            (output_path / 'dot' / f'{role_id}.dot').write_text(dot_str)
            (output_path / 'logs' / f'{role_id}.txt').write_text(log_str)
        if error_str:
            (output_path / 'errors' / f'{role_id}.txt').write_text(error_str)


@group.command()
@click.argument('input', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
@click.argument('output', type=click.Path(dir_okay=True, file_okay=False, writable=True))
def extract_debug(input: str, output: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level='DEBUG')
    input_path = Path(input)
    output_path = Path(output)
    (output_path / 'neo4j').mkdir(exist_ok=True, parents=True)
    (output_path / 'graphml').mkdir(exist_ok=True, parents=True)
    (output_path / 'dot').mkdir(exist_ok=True, parents=True)
    (output_path / 'errors').mkdir(exist_ok=True, parents=True)

    task = (input_path.name, input_path)
    (role_id, neo4j_str, graphml_str, dot_str, error_str, _) = extract_one(task, log_reset=False)
    if neo4j_str:
        (output_path / 'neo4j' / f'{role_id}.txt').write_text(neo4j_str)
        (output_path / 'graphml' / f'{role_id}.xml').write_text(graphml_str)
        (output_path / 'dot' / f'{role_id}.dot').write_text(dot_str)
    if error_str:
        (output_path / 'errors' / f'{role_id}.txt').write_text(error_str)


@group.command()
@click.argument('input', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
@click.argument('output', type=click.Path(dir_okay=True, file_okay=False, writable=True))
def detect(input: str, output: str) -> None:
    input_path = Path(input) / 'graphml'
    output_path = Path(output)
    output_path.mkdir(exist_ok=True, parents=True)

    roles = [path for path in input_path.iterdir() if path.name.endswith('.xml')]

    conflict_checker = ConflictingVariables(output_path)
    with (output_path / 'report.txt').open('w') as output_stream:
        for results in process_map(detect_one_graph, roles, chunksize=50, desc='Detecting'):
            if len(results) == 2:
                path, error = results
                logger.error(f'Failed to perform detection for {path}: {error}')
                continue
            role_name, warnings, def_vars = results
            if warnings:
                output_stream.write(role_name + '\n')
                output_stream.write('-----\n')
                output_stream.write('\n'.join('* ' + indent(res.description, '  ').lstrip() for res in warnings))
                output_stream.write('\n')
            conflict_checker.add_all(role_name, def_vars)

        conflict_checker.process()
        conflicts = conflict_checker.results
        output_stream.write('------------------\n')
        output_stream.write(f'Found {len(conflicts)} Possible Variable Conflicts\n')
        output_stream.write('------------------\n')


@group.command()
@click.argument('source', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
@click.argument('target', type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True))
def compare(source: str, target: str) -> None:
    source_path = Path(source)
    target_path = Path(target)

    from tests.helpers.graph_matchers import assert_graphs_match

    for p in tqdm(source_path.iterdir()):
        if not p.is_file() or not p.name.endswith('.xml'):
            continue
        if not (target_path / p.name).is_file():
            tqdm.write('No correspondence found for ' + p.name)

        try:
            src_graph = graphml.import_graph(p.read_text())
            target_graph = graphml.import_graph((target_path / p.name).read_text())
            assert_graphs_match(src_graph, target_graph)
        except BaseException as e:
            tqdm.write(p.name + ': ' + str(e))


if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr, level='INFO')
    group()
