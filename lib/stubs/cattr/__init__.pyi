from .converters import Converter as Converter, Converter as GenConverter, UnstructureStrategy as UnstructureStrategy
from typing import Any

global_converter: Converter
unstructure = global_converter.unstructure
structure = global_converter.structure
structure_attrs_fromtuple: Any
structure_attrs_fromdict: Any
