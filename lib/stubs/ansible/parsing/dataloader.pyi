from __future__ import annotations

from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject

class DataLoader:
    def __init__(self) -> None: ...
    def load(
        self,
        data: str,
        file_name: str = ...,
        show_content: bool = ...,
        json_only: bool = ...,
    ) -> AnsibleBaseYAMLObject: ...
    def load_from_file(
        self,
        file_name: str,
        cache: bool = ...,
        unsafe: bool = ...,
        json_only: bool = ...,
    ) -> AnsibleBaseYAMLObject: ...
    def find_vars_files(
        self,
        path: str,
        name: str,
        extensions: list[str] | None = ...,
        allow_dir: bool = ...,
    ) -> list[bytes]: ...
