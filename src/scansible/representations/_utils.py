from __future__ import annotations

from typing import Any, Callable, Union

import types

import attrs
from attrs_strict import AttributeTypeError, type_validator as old_type_validator


def _convert_union_type(type_: Any) -> object:
    if isinstance(type_, types.UnionType):
        return Union.__getitem__(tuple(_convert_union_type(arg) for arg in type_.__args__))

    if not isinstance(type_, types.GenericAlias):
        return type_

    if type_.__origin__ in (list, dict):
        return types.GenericAlias(type_.__origin__, tuple(_convert_union_type(arg) for arg in type_.__args__))
    return type_


# Patch for https://github.com/bloomberg/attrs-strict/issues/80
def type_validator(empty_ok: bool = True) -> Callable[[Any, attrs.Attribute[Any], Any], None]:
    old_validator = old_type_validator(empty_ok)

    # Convert types.UnionType into typing.Union recursively.
    def convert_types(attribute: attrs.Attribute[Any]) -> None:
        # Use object.__setattr__ to workaround frozen attr.Attribute
        object.__setattr__(attribute, 'type', _convert_union_type(attribute.type))

    def converting_validator(instance: Any, attribute: attrs.Attribute[Any], field: Any) -> None:
        try:
            convert_types(attribute)
            old_validator(instance, attribute, field)
        except AttributeTypeError as e:
            # from __future__ import annotations leads to the original type
            # annotation being a string, so it's possible that we couldn't
            # convert the union type earlier because we got a string instead
            # of types.UnionType. By now, attrs-strict should've resolved those
            # types, so try again.
            if not e.__context__ or e.__context__.__class__.__name__ != '_StringAnnotationError':
                raise
            convert_types(attribute)
            old_validator(instance, attribute, field)

    return converting_validator
