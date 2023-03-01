from typing import NamedTuple

from scansible.representations.pdg.extractor.context import ExtractionContext

from . import security as security
from . import semantics as semantics
from .reporter import *


class CheckResult(NamedTuple):
    #: The rule that was triggered.
    rule_name: str
    #: Location in the code of the smell (file:line:column)
    location: NodeLocation | str  # TODO: NodeLocation only, needs changes in security smells


def run_all_checks(
    extraction_context: ExtractionContext,
    db_host: str,
    enable_security: bool = True,
    enable_semantics: bool = True,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    if enable_security:
        results.extend(
            CheckResult(res.rule_name, res.source_location)
            for res in security.run_all_checks(extraction_context.graph, db_host)
        )
    if enable_semantics:
        results.extend(
            CheckResult(f"{res.rule_category}: {res.rule_name}", res.location)
            for res in semantics.run_all_checks(
                extraction_context.graph, extraction_context.visibility_information
            )
        )
    return results
