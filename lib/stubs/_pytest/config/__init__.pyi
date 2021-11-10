from typing import Any, TypeVar

from . import argparsing as argparsing

_T = TypeVar('_T')

class Config:
    rootdir: str

    def getoption(self, name: str, default: _T = ..., skip: bool = ...) -> _T: ...
    def addinivalue_line(self, name: str, value: str) -> None: ...
