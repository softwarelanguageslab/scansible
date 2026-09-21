from __future__ import annotations

from typing import final, override

from collections.abc import Sequence
from contextlib import AbstractContextManager

from loguru import logger

from scansible import ast
from scansible.utils import actions

from ... import representation as rep
from ..result import BuildResult
from ._dynamic_includes import DynamicIncludesBuilder


@final
class IncludeTaskBuilder(DynamicIncludesBuilder[ast.TaskFile]):
    CONTENT_TYPE = "task file"

    @override
    def _extract_included_name(
        self, args: dict[ast.StrLiteral, ast.AnyExpression]
    ) -> ast.AnyExpression:
        return args.pop(ast.StrLiteral("_raw_params"), None)

    @override
    def _load_content(
        self, included_name: str
    ) -> AbstractContextManager[ast.TaskFile | None]:
        return self.context.include_ctx.load_and_enter_task_file(
            included_name, self.location
        )

    @override
    def _get_filename_candidates(self, included_name_pattern: str) -> set[str]:
        logger.warning("Conditions for include_tasks not fully set yet!")
        return self.context.include_ctx.find_matching_task_files(included_name_pattern)

    @override
    def _file_exists(self, name: str) -> bool:
        return self.context.include_ctx.find_task_file(name) is not None

    @override
    def _check_conditions(self) -> None:
        if actions.is_import_tasks(self.task.action) and self.context.active_conditions:
            self.logger.warning(
                "Conditions active during static include, semantics unknown!"
            )

    @override
    def _build_included_content(
        self, included_content: ast.TaskFile, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        # Import here to prevent recursive imports
        from ..task_lists import TaskListBuilder  # noqa: PLC0415

        return TaskListBuilder(self.context, included_content.tasks).build_tasks(
            predecessors
        )
