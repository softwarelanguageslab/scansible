from __future__ import annotations

from typing import Any, Optional, Union

from gitdb.utils.encoding import force_bytes as force_bytes  # type: ignore
from gitdb.utils.encoding import force_text as force_text

is_win: bool
is_posix: bool
is_darwin: bool
defenc: str

def safe_decode(s: Optional[Union[bytes, str]]) -> str: ...
def safe_encode(s: Optional[Union[bytes, str]]) -> bytes: ...
def win_encode(s: Optional[Union[bytes, str]]) -> bytes: ...
