from ansible.playbook.base import Base
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.taggable import Taggable

class Play(Base, Taggable, CollectionSearch):
    def __init__(self) -> None: ...