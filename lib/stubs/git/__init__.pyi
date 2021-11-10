from typing import Any, AnyStr, Optional, Union

from .repo import Repo as Repo
from .exc import *
from .objects import *
from .refs import *
from .diff import *
from .db import *
from .remote import *
# from .index import *
from .cmd import Git as Git
from .config import GitConfigParser as GitConfigParser
from .util import Actor as Actor, BlockingLockFile as BlockingLockFile, LockFile as LockFile, Stats as Stats, rmtree as rmtree

from pathlib import Path
_Path = Union[Path, str]

GIT_OK: bool

def refresh(path: Optional[_Path] = ...) -> None: ...
