from __future__ import annotations

from typing import ContextManager

from collections.abc import Sequence

from scansible.representations.structural.representation import AnyValue, VariableFile

from ... import representation as rep
from ..expressions import EnvironmentType
from ..result import ExtractionResult
from ..variables import VariablesExtractor
from ._dynamic_includes import DynamicIncludesExtractor


class IncludeVarsTaskExtractor(DynamicIncludesExtractor[VariableFile]):
    CONTENT_TYPE = "variable file"
    TASK_VARS_SCOPE_LEVEL = EnvironmentType.TASK_VARS

    def _extract_included_name(self, args: dict[str, AnyValue]) -> AnyValue:
        return args.pop("_raw_params", None)

    def _load_content(self, included_name: str) -> ContextManager[VariableFile | None]:
        return self.context.include_ctx.load_and_enter_var_file(
            included_name, self.location
        )

    def _get_filename_candidates(
        self,
        included_name_candidates: set[str],
    ) -> set[str]:
        return self.context.include_ctx.find_matching_var_files(
            included_name_candidates
        )

    def _extract_included_content(
        self, included_content: VariableFile, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        return VariablesExtractor(
            self.context, included_content.variables
        ).extract_variables(EnvironmentType.INCLUDE_VARS)

    def extract_condition(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        # Don't include these condition nodes into the CFG, see SetFactExtractor.
        # Therefore, we won't provide any predecessors when extracting the conditions.
        return super().extract_condition([])

    def _create_result(
        self,
        included_result: ExtractionResult,
        current_predecessors: Sequence[rep.ControlNode],
        added_conditional_nodes: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        # HACK: If the placeholder task was created because of an error, we need
        # to properly instantiate the CFG since there is now a control node that
        # was added.
        if included_result.added_control_nodes:
            if added_conditional_nodes:
                first_conditional = added_conditional_nodes[0]
                for pred in current_predecessors:
                    self.context.graph.add_edge(pred, first_conditional, rep.ORDER)

            return super()._create_result(
                included_result, current_predecessors, added_conditional_nodes
            )

        # See above, we don't want the conditional nodes to be included in the CFG,
        # so we don't provide them as next predecessors.
        return (
            super()
            ._create_result(
                included_result, current_predecessors, added_conditional_nodes
            )
            .replace_next_predecessors(current_predecessors)
        )
