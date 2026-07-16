"""AST nodes representing Jinja2 expressions used in Ansible content.

For now, these nodes are validated subclasses of plain `str` and can be used just like an actual `str`.
In the future, they may become full-fledged `ASTNode` instances with parsed expressions.
"""

from __future__ import annotations

from typing import Self

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


def is_template(expr: str) -> bool:
    templar = Templar(DataLoader())
    return templar.is_template(expr)


class Expression(str):
    """AST node representing a Jinja2 expression."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: str) -> Expression:
            if not is_template(value):
                raise ValueError("not a valid expression")
            return cls(value)

        return core_schema.no_info_after_validator_function(
            validate, core_schema.str_schema()
        )


class BareExpression(str):
    """AST node representing an Ansible expression without surrounding braces."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: str) -> Self:
            # FIXME: We need validation here to make sure it's a correct condition, but
            # the validation is complex and currently lives in the PDG builder.
            # When doing such validation, we may as well parse the expressions/conditions too.
            return cls(value)

        return core_schema.no_info_after_validator_function(
            validate, core_schema.str_schema()
        )


class Condition(BareExpression):
    """AST node representing an Ansible condition.

    Ansible conditions are Jinja2 expressions without surrounding braces.
    """
