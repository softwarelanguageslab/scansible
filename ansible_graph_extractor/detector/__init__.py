from __future__ import annotations

from typing import cast, Iterable
from pathlib import Path
from textwrap import indent
from collections import Counter
from contextlib import AbstractContextManager, ExitStack
from tqdm.contrib.concurrent import process_map
from tqdm import tqdm
import csv
import json

from ..io import graphml
from ..models.graph import Graph
from ..extractor.context import VisibilityInformation
from ..extractor.var_context import ScopeLevel
from .base import RuleResult
from .reuse_nonidempotent_expression_rule import ReuseNonIdempotentExpressionRule
from .reuse_changed_rule import ReuseChangedVariableRule
from .unnecessary_set_fact import UnnecessarySetFactRule
from .unnecessary_include_vars import UnnecessaryIncludeVarsRule
from .unconditional_override_rule import UnconditionalOverrideRule
from .override_unused_rule import UnusedOverriddenRule
from .conflicting_variables import getvars
from .sanity_num_tasks import SanityCheckNumberOfTasksRule
from .conflicting_variables import ConflictingVariables
from loguru import logger

ALL_RULES = [
    ReuseNonIdempotentExpressionRule(),
    ReuseChangedVariableRule(),
    UnnecessarySetFactRule(),
    UnnecessaryIncludeVarsRule(),
    UnconditionalOverrideRule(),
    UnusedOverriddenRule(),
    # SanityCheckNumberOfTasksRule(),
]

def detect_all(graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
    return [res for rule in ALL_RULES for res in rule.scan(graph, visinfo)]

SuccessResult = tuple[str, str, list[RuleResult], list[tuple[str, int]]]
FailResult = tuple[Path, Exception]

def detect_one_graph(args: tuple[Path, Path, str, str]) -> SuccessResult | FailResult:
    graphml_path, aux_path, role_id, role_version = args
    try:
        graph = graphml.import_graph(graphml_path.read_text(), role_id, role_version)
        visinfo = VisibilityInformation.load(aux_path.read_text())
        results = detect_all(graph, visinfo)

        return graph.role_name, graph.role_version, results, list(getvars(graph))
    except Exception as err:
        print(f'{graphml_path}: {type(err).__name__}: {err}')
        # logger.exception(err)
        return graphml_path, err


class ResultProcessor(AbstractContextManager['ResultProcessor']):
    def __init__(self, output_path: Path) -> None:
        self.warnings_csv = (output_path / 'warnings.csv').open('w')
        self.warnings_writer = csv.writer(self.warnings_csv)
        self.roles_csv = (output_path / 'roles.csv').open('w')
        self.roles_writer = csv.writer(self.roles_csv)
        self.variables_csv = (output_path / 'defined_variables.csv').open('w')
        self.variables_writer = csv.writer(self.variables_csv)

        self.output_path = output_path
        self.report_buffer_lines: list[str] = []
        self._exit_stack = ExitStack()
        self.warning_type_counter: Counter[str] = Counter()
        self.conflict_checker = ConflictingVariables()

        self.warnings_writer.writerow(['role_name', 'role_version', 'warning_category', 'warning_name', 'warning_subname', 'warning_header', 'warning_message', 'warning_location'])
        self.roles_writer.writerow(['role_name', 'role_version'])
        self.variables_writer.writerow(['role_name', 'role_version', 'var_name', 'precedence_level'])

    def __enter__(self) -> ResultProcessor:
        self._exit_stack.enter_context(self.warnings_csv)
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._exit_stack.close()
        conflicts = self.conflict_checker.process()
        self._write_report(conflicts)
        self._write_conflicts(conflicts)

    def process_results(self, results: SuccessResult) -> None:
        role_name, role_version, warnings, defined_variables = results

        self.roles_writer.writerow([role_name, role_version])

        if warnings:
            self.report_buffer_lines.extend((role_name, '-----'))
        for warning in warnings:
            self._add_warning_to_buffer(warning)
            self._add_warning_to_csv(warning)

        if role_version == 'HEAD':
            self.conflict_checker.add_all(role_name, defined_variables)

        self._write_defined_variables(role_name, role_version, defined_variables)

        if warnings:
            self.report_buffer_lines.append('')

    def _add_warning_to_buffer(self, warning: RuleResult) -> None:
        rule_prefix = f'{warning.rule_category}::{warning.rule_name}'
        if warning.rule_subname:
            rule_prefix += f'::{warning.rule_subname}'

        self.report_buffer_lines.extend([
                f'* {warning.location}: {rule_prefix}',
                indent(warning.rule_header, '  '),
                indent(warning.rule_message, '  '),
        ])
        self.warning_type_counter[rule_prefix] += 1

    def _add_warning_to_csv(self, warning: RuleResult) -> None:
        self.warnings_writer.writerow([
            warning.role_name,
            warning.role_version,
            warning.rule_category,
            warning.rule_name,
            warning.rule_subname,
            warning.rule_header,
            warning.rule_message,
            warning.location,
        ])

    def _write_defined_variables(self, role_name: str, role_version: str, defined_variables: list[tuple[str, int]]) -> None:
        # Sorting so that higher precedence version with same name gets added later, therefore overwriting
        max_var_defs = {name: prec for name, prec in sorted(defined_variables, key=lambda x: x[1])}
        for name, prec in max_var_defs.items():
            prec_str = ScopeLevel(prec).name
            self.variables_writer.writerow([role_name, role_version, name, prec_str])

    def _write_report(self, conflicts: list[tuple[str, str, int, str, int]]) -> None:
        report_path = self.output_path / 'report.txt'
        with report_path.open('w') as output_stream:
            output_stream.write('------------------\n')
            output_stream.write('Warnings summary:\n')
            for rule_name, rule_count in sorted(self.warning_type_counter.items(), key=lambda x: x[1]):
                output_stream.write(f'{rule_count}\t{rule_name}\n')

            output_stream.write('\n------------------\n')
            output_stream.write(f'Found {len(conflicts)} Possible Variable Conflicts\n')

            output_stream.write('\n------------------\n')
            output_stream.write('\n'.join(self.report_buffer_lines))

    def _write_conflicts(self, conflicts: list[tuple[str, str, int, str, int]]) -> None:
        with (self.output_path / 'conflicts.csv').open('w') as f:
            writer = csv.writer(f)
            writer.writerow(['var_name', 'high_role', 'high_precedence_level', 'low_role', 'low_precedence_level'])
            for var_name, hi_role, hi_level, lo_role, lo_level in conflicts:
                hi_level_name = ScopeLevel(hi_level).name
                lo_level_name = ScopeLevel(lo_level).name
                writer.writerow([var_name, hi_role, hi_level_name, lo_role, lo_level_name])


def main(input_path: Path, output_path: Path) -> None:
    results: tuple[str, list[RuleResult], list[tuple[str, int]]] | tuple[Path, Exception]
    tasks = list(create_tasks(input_path))
    with ResultProcessor(output_path) as result_processor:
        for results in process_map(detect_one_graph, tasks, chunksize=50, desc='Detecting'):
            if len(results) == 2:
                path, error = cast(tuple[Path, Exception], results)
                logger.error(f'Failed to perform detection for {path}: {error}')
                continue

            result_processor.process_results(cast(tuple[str, str, list[RuleResult], list[tuple[str, int]]], results))

def create_tasks(input_path: Path) -> Iterable[tuple[Path, Path, str, str]]:
    graphml_root = input_path / 'graphml'
    aux_root = input_path / 'aux'
    index_path = input_path / 'index.json'
    if index_path.is_file():
        index = json.loads(index_path.read_text())
        for graphml_file_str in tqdm(index, 'Scanning for graphs'):
            graphml_file = Path(graphml_file_str)
            # assert graphml_file.is_file(), f'Could not find {graphml_file}'
            yield graphml_file, get_aux_path(graphml_root, graphml_file, aux_root), *get_default_role_id_and_version(graphml_root, graphml_file)
    else:
        print('Slowly scanning for graph files')
        for graphml_file in graphml_root.glob('**/*.xml'):
            yield graphml_file, get_aux_path(graphml_root, graphml_file, aux_root), *get_default_role_id_and_version(graphml_root, graphml_file)

def get_aux_path(graphml_root: Path, graphml_file: Path, aux_root: Path) -> Path:
    return aux_root / graphml_file.relative_to(graphml_root).with_suffix('.vis.json')

def get_default_role_id_and_version(graphml_root: Path, graphml_file: Path) -> tuple[str, str]:
    if graphml_file.parent == graphml_root:
        return graphml_file.stem, 'HEAD'

    rel_file = graphml_file.relative_to(graphml_root)
    return rel_file.parts[0], rel_file.stem
