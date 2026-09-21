from __future__ import annotations

from typing import final, override

from collections.abc import Sequence
from contextlib import AbstractContextManager

from loguru import logger

from scansible import ast

from ... import representation as rep
from ..result import BuildResult
from ..semantics import EnvironmentType
from ..variables import VariablesBuilder
from ._dynamic_includes import DynamicIncludesBuilder


@final
class IncludeVarsTaskBuilder(DynamicIncludesBuilder[ast.VariableFile]):
    CONTENT_TYPE = "variable file"
    TASK_VARS_SCOPE_LEVEL = EnvironmentType.TASK_VARS

    @override
    def _extract_included_name(
        self, args: dict[ast.StrLiteral, ast.AnyExpression]
    ) -> ast.AnyExpression:
        return args.pop(ast.StrLiteral("_raw_params"), None)

    @override
    def _load_content(
        self, included_name: str
    ) -> AbstractContextManager[ast.VariableFile | None]:
        return self.context.include_ctx.load_and_enter_var_file(
            included_name, self.location
        )

    @override
    def _get_filename_candidates(self, included_name_pattern: str) -> set[str]:
        logger.warning("Conditions for include_vars not set yet!")
        return self.context.include_ctx.find_matching_var_files(included_name_pattern)

    @override
    def _file_exists(self, name: str) -> bool:
        return self.context.include_ctx.find_var_file(name) is not None

    @override
    def _build_included_content(
        self,
        included_content: ast.VariableFile,
        predecessors: Sequence[rep.ControlNode],
    ) -> BuildResult:
        return (
            VariablesBuilder(self.context, included_content.variables)
            .build_variables(EnvironmentType.INCLUDE_VARS)
            .replace_next_predecessors(predecessors)
        )
