from __future__ import annotations

from typing import ContextManager

from collections.abc import Sequence

from scansible.representations.structural.representation import AnyValue, VariableFile

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from ..variables import VariablesExtractor
from ._dynamic_includes import DynamicIncludesExtractor


class IncludeVarsTaskExtractor(DynamicIncludesExtractor[VariableFile]):
    CONTENT_TYPE = "variable file"
    TASK_VARS_SCOPE_LEVEL = ScopeLevel.TASK_VARS

    def _extract_included_name(self, args: dict[str, AnyValue]) -> AnyValue:
        return args.pop("_raw_params", None)

    def _load_content(self, included_name: str) -> ContextManager[VariableFile | None]:
        return self.context.include_ctx.load_and_enter_var_file(
            included_name, self.location
        )

    def _extract_included_content(
        self, included_content: VariableFile, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        return VariablesExtractor(
            self.context, included_content.variables
        ).extract_variables(ScopeLevel.INCLUDE_VARS)

    def extract_condition(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        # Don't include these condition nodes into the CFG, see SetFactExtractor.
        # Therefore, we won't provide any predecessors.
        return super().extract_condition([])

    def _create_result(
        self,
        included_result: ExtractionResult,
        current_predecessors: Sequence[rep.ControlNode],
        added_conditional_nodes: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        # See above, we don't want the conditional nodes to be included in the CFG,
        # so we don't provide them as next predecessors.
        return (
            super()
            ._create_result(
                included_result, current_predecessors, added_conditional_nodes
            )
            .replace_next_predecessors(current_predecessors)
        )
