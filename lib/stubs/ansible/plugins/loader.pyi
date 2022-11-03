from typing import Any

class PluginLoader:

    def has_plugin(self, name: str, collection_list: Any = ...) -> bool: ...
    def __contains__(self, name: str) -> bool: ...

lookup_loader: PluginLoader
