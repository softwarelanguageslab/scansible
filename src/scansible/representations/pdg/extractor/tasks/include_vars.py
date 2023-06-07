from __future__ import annotations

from typing import ContextManager

from collections.abc import Sequence

from loguru import logger

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
        included_name_pattern: str,
    ) -> set[str]:
        logger.warning("Conditions for include_vars not set yet!")
        return self.context.include_ctx.find_matching_var_files(included_name_pattern)

    def _file_exists(self, name: str) -> bool:
        return self.context.include_ctx.find_var_file(name) is not None

    def _extract_included_content(
        self, included_content: VariableFile, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        return (
            VariablesExtractor(self.context, included_content.variables)
            .extract_variables(EnvironmentType.INCLUDE_VARS)
            .replace_next_predecessors(predecessors)
        )
