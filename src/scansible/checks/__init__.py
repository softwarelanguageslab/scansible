from __future__ import annotations

from typing import NamedTuple

from scansible.representations.pdg.extractor.context import ExtractionContext

from . import security as security
from . import semantics as semantics
from .reporter import *


class CheckResult(NamedTuple):
    #: The rule that was triggered.
    rule_name: str
    #: Location in the code of the smell (file:line:column)
    location: NodeLocation | None


def _convert_location(loc: str | None) -> NodeLocation | None:
    # FIXME: All checks should just return NodeLocation by default
    if loc is None:
        return loc

    try:
        file, line, column = loc.split(":")
        return NodeLocation(file=file, line=int(line), column=int(column))
    except ValueError:
        return None


def run_all_checks(
    extraction_context: ExtractionContext,
    enable_security: bool = True,
    enable_semantics: bool = True,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    if enable_security:
        for res in security.run_all_checks(extraction_context.graph):
            description = f"{res.rule_name}: {res.__class__.rule_description}"
            results.append(
                CheckResult(description, _convert_location(res.sink_location))
            )
            if res.sink_location != res.source_location:
                results.append(
                    CheckResult(description, _convert_location(res.source_location))
                )
    if enable_semantics:
        results.extend(
            CheckResult(f"{res.rule_category}: {res.rule_header}", res.location)
            for res in semantics.run_all_checks(
                extraction_context.graph, extraction_context.visibility_information
            )
        )
    return results
