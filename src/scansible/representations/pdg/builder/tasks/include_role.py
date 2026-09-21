from __future__ import annotations

from typing import final, override

from collections.abc import Sequence
from contextlib import AbstractContextManager

from loguru import logger

from scansible.representations import ast

from ... import representation as rep
from ..result import BuildResult
from ._dynamic_includes import DynamicIncludesBuilder


# TODO: Properly distinguish between private and public role includes, i.e.,
# whether the scopes pop.
@final
class IncludeRoleBuilder(DynamicIncludesBuilder[ast.Role]):
    CONTENT_TYPE = "role"

    @override
    def _extract_included_name(
        self, args: dict[ast.StrLiteral, ast.AnyExpression]
    ) -> ast.AnyExpression:
        included_name = args.pop(ast.StrLiteral("_raw_params"), None)
        if not included_name:
            included_name = args.pop(ast.StrLiteral("name"), None)

        return included_name

    @override
    def _load_content(
        self, included_name: str
    ) -> AbstractContextManager[ast.Role | None]:
        return self.context.include_ctx.load_and_enter_role(
            included_name, self.location
        )

    @override
    def _get_filename_candidates(self, included_name_pattern: str) -> set[str]:
        logger.warning("Conditions for include_role not set yet!")
        return self.context.include_ctx.find_matching_roles(included_name_pattern)

    @override
    def _file_exists(self, name: str) -> bool:
        return self.context.include_ctx.find_role(name) is not None

    @override
    def _build_included_content(
        self, included_content: ast.Role, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        # Import here to prevent recursive imports
        from ..role import RoleBuilder  # noqa: PLC0415

        return RoleBuilder(self.context, included_content).build_role(predecessors)
