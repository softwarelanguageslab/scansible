from .base import Base, Value
from .conditional import Conditional
from .taggable import Taggable

class PlaybookInclude(Base, Conditional, Taggable):
    import_playbook: str = ...
    vars: dict[str, Value] = ...
