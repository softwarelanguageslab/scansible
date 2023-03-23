from __future__ import annotations

from typing import ContextManager

from collections.abc import Sequence

from scansible.representations.structural.representation import AnyValue, Role

from ... import representation as rep
from ..result import ExtractionResult
from ._dynamic_includes import DynamicIncludesExtractor


class IncludeRoleExtractor(DynamicIncludesExtractor[Role]):
    CONTENT_TYPE = "role"

    def _extract_included_name(self, args: dict[str, AnyValue]) -> AnyValue:
        included_name = args.pop("_raw_params", None)
        if not included_name:
            included_name = args.pop("name", None)

        return included_name

    def _load_content(self, included_name: str) -> ContextManager[Role | None]:
        return self.context.include_ctx.load_and_enter_role(
            included_name, self.location
        )

    def _extract_included_content(
        self, included_content: Role, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        from ..role import RoleExtractor

        return RoleExtractor(self.context, included_content).extract_role(predecessors)
