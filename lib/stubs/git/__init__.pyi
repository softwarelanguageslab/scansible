from __future__ import annotations

from typing import Any, AnyStr, Optional, Union

from pathlib import Path

# from .index import *
from .cmd import Git as Git
from .config import GitConfigParser as GitConfigParser
from .db import *
from .diff import *
from .exc import *
from .objects import *
from .refs import *
from .remote import *
from .repo import Repo as Repo
from .util import Actor as Actor
from .util import BlockingLockFile as BlockingLockFile
from .util import LockFile as LockFile
from .util import Stats as Stats
from .util import rmtree as rmtree

_Path = Union[Path, str]

GIT_OK: bool

def refresh(path: Optional[_Path] = ...) -> None: ...
