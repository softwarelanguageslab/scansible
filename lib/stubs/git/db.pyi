from gitdb.db import GitDB as GitDB, LooseObjectDB  # type: ignore
from gitdb.base import OStream, OInfo  # type: ignore
from typing import Any

from .cmd import Git

class GitCmdObjectDB(LooseObjectDB):  # type: ignore
    def __init__(self, root_path: Any, git: Git) -> None: ...
    def info(self, sha: bytes) -> OInfo: ...  # type: ignore
    def stream(self, sha: bytes) -> OStream: ...  # type: ignore
    def partial_to_complete_sha_hex(self, partial_hexsha: bytes) -> bytes: ...
