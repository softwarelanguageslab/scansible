from __future__ import annotations

from typing import ContextManager, cast

from collections.abc import Sequence

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
        included_name_candidates: set[str],
    ) -> set[str]:
        return self.context.include_ctx.find_matching_task_files(
            included_name_candidates
        )

    def extract_condition(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        if actions.is_import_tasks(self.task.action):
            self.logger.warning("Not sure how to handle conditional on static import")
            # Ignore these.
            return ExtractionResult.empty(predecessors)

        return super().extract_condition(predecessors)

    def _extract_included_content(
        self, included_content: TaskFile, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        from ..task_lists import TaskListExtractor

        return TaskListExtractor(
            self.context, cast(Sequence[Block | Task], included_content.tasks)
        ).extract_tasks(predecessors)
