from __future__ import annotations

from typing import ContextManager, cast

from collections.abc import Sequence

from loguru import logger

from scansible.representations.structural.representation import (
    AnyValue,
    Block,
    Task,
    TaskFile,
)
from scansible.utils import actions

from ... import representation as rep
from ..result import ExtractionResult
from ._dynamic_includes import DynamicIncludesExtractor


class IncludeTaskExtractor(DynamicIncludesExtractor[TaskFile]):
    CONTENT_TYPE = "task file"

    def _extract_included_name(self, args: dict[str, AnyValue]) -> AnyValue:
        return args.pop("_raw_params", None)

    def _load_content(self, included_name: str) -> ContextManager[TaskFile | None]:
        return self.context.include_ctx.load_and_enter_task_file(
            included_name, self.location
        )

    def _get_filename_candidates(
        self,
        included_name_pattern: str,
    ) -> set[str]:
        logger.warning("Conditions for include_tasks not fully set yet!")
        return self.context.include_ctx.find_matching_task_files(included_name_pattern)

    def _file_exists(self, name: str) -> bool:
        return self.context.include_ctx.find_task_file(name) is not None

    def _check_conditions(self) -> None:
        if actions.is_import_tasks(self.task.action) and self.context.active_conditions:
            self.logger.warning(
                "Conditions active during static include, semantics unknown!"
            )

    def _extract_included_content(
        self, included_content: TaskFile, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        from ..task_lists import TaskListExtractor

        return TaskListExtractor(
            self.context, cast(Sequence[Block | Task], included_content.tasks)
        ).extract_tasks(predecessors)
