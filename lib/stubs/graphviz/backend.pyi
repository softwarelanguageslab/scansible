from typing import Any, Literal, Optional, Set, Tuple

ENGINES: Set[_EngineValue]
FORMATS: Set[_FormatValue]
RENDERERS: Set[_RendererValue]
FORMATTERS: Set[_FormatterValue]

_EngineValue = Literal[
    'dot', 'neato', 'twopi', 'circo', 'fdp', 'sfdp', 'patchwork', 'osage',
]

_FormatValue = Literal[
    'bmp',
    'canon', 'dot', 'gv', 'xdot', 'xdot1.2', 'xdot1.4',
    'cgimage',
    'cmap',
    'eps',
    'exr',
    'fig',
    'gd', 'gd2',
    'gif',
    'gtk',
    'ico',
    'imap', 'cmapx',
    'imap_np', 'cmapx_np',
    'ismap',
    'jp2',
    'jpg', 'jpeg', 'jpe',
    'json', 'json0', 'dot_json', 'xdot_json',  # Graphviz 2.40
    'pct', 'pict',
    'pdf',
    'pic',
    'plain', 'plain-ext',
    'png',
    'pov',
    'ps',
    'ps2',
    'psd',
    'sgi',
    'svg', 'svgz',
    'tga',
    'tif', 'tiff',
    'tk',
    'vml', 'vmlz',
    'vrml',
    'wbmp',
    'webp',
    'xlib',
    'x11',
]

_RendererValue = Literal[
    'cairo',
    'dot',
    'fig',
    'gd',
    'gdiplus',
    'map',
    'pic',
    'pov',
    'ps',
    'svg',
    'tk',
    'vml',
    'vrml',
    'xdot',
]

_FormatterValue = Literal['cairo', 'core', 'gd', 'gdiplus', 'gdwbmp', 'xlib']

PLATFORM: str

class ExecutableNotFound(RuntimeError): ...
class RequiredArgumentError(Exception): ...
class CalledProcessError: ...

def render(engine: _EngineValue, format: _FormatValue, filepath: str, renderer: Optional[_RendererValue] = ..., formatter: Optional[_FormatterValue] = ..., quiet: bool = ...) -> str: ...
def pipe(engine: _EngineValue, format: _FormatValue, data: bytes, renderer: Optional[_RendererValue] = ..., formatter: Optional[_FormatterValue] = ..., quiet: bool = ...) -> bytes: ...
def version() -> Tuple[int, ...]: ...
def view(filepath: str, quiet: bool = ...) -> None: ...
