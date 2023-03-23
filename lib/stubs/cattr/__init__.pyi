from __future__ import annotations

from typing import Any

from .converters import Converter as Converter
from .converters import UnstructureStrategy as UnstructureStrategy

global_converter: Converter
unstructure = global_converter.unstructure
structure = global_converter.structure
structure_attrs_fromtuple: Any
structure_attrs_fromdict: Any
