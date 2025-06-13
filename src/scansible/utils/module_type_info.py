"""Information about Ansible modules and their parameter types."""

from __future__ import annotations

from typing import Any

import json
import subprocess
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

import rich.progress
from attrs import Attribute, asdict, field, frozen
from loguru import logger

from scansible.utils import first
from scansible.utils.type_validators import type_validator


@frozen
class OptionInfo:
    description: Sequence[str] = field(validator=type_validator())
    type: str | None = field(validator=type_validator())
    required: bool = field(validator=type_validator())
    default: Any | None = field(validator=type_validator())
    version_added: Any | None = field(validator=type_validator())
    version_added_collection: Any | None = field(validator=type_validator())
    aliases: Sequence[str] = field(validator=type_validator())
    elements: str | None = field(validator=type_validator())
    choices: Sequence[Any] | None = field(validator=type_validator())
    suboptions: Mapping[str, OptionInfo] | None = field(validator=type_validator())

    @classmethod
    def parse(cls, info: dict[str, Any], name: str, mod_name: str) -> OptionInfo:  # type: ignore[misc]
        # Copy so we can mutate
        info = dict(info)

        inst = cls(
            description=info.pop("description"),
            type=info.pop("type", None),
            default=info.pop("default", None),
            required=info.pop("required", False),
            version_added=info.pop("version_added", None),
            version_added_collection=info.pop("version_added_collection", None),
            aliases=info.pop("aliases", []),
            elements=info.pop("elements", None),
            choices=info.pop("choices", None),
            suboptions={
                subname: OptionInfo.parse(value, f"{name}.{subname}", mod_name)
                for subname, value in info.pop("suboptions").items()
            }
            if info.get("suboptions")
            else info.pop("suboptions", None),
        )

        for leftover_key in info:
            logger.warning(
                f"Leftover option attribute for {mod_name} {name}: {leftover_key}"
            )

        return inst


ReturnInfo = Mapping[str, Any]
AttributeInfo = Mapping[str, Any]


@frozen
class ModuleInfo:
    collection: str = field(validator=type_validator())
    short_name: str = field(validator=type_validator())
    description: Sequence[str] = field(validator=type_validator())
    short_description: str = field(validator=type_validator())

    author: Sequence[str] = field(validator=type_validator())
    has_action: bool = field(validator=type_validator())
    notes: Sequence[str] = field(validator=type_validator())
    requirements: Sequence[str] = field(validator=type_validator())

    attributes: Mapping[str, AttributeInfo] = field(validator=type_validator())
    options: Mapping[str, OptionInfo] = field(validator=type_validator())
    examples: str = field(validator=type_validator())
    metadata: object = field(validator=type_validator(), default=None)
    returns: Mapping[str, ReturnInfo] | None = field(
        validator=type_validator(), default=None
    )

    @property
    def qualified_name(self) -> str:
        return f"{self.collection}.{self.short_name}"

    @property
    def all_option_names(self) -> set[str]:
        options: set[str] = set()
        for optname, opt in self.options.items():
            options.add(optname)
            options |= set(opt.aliases)
        return options

    def get_canonical_option_name(self, option_name: str) -> str | None:
        if option_name in self.options:
            return option_name

        return first(
            canonical_name
            for canonical_name, opt in self.options.items()
            if option_name in opt.aliases
        )

    @classmethod
    def load(cls, info: dict[str, Any]) -> ModuleInfo:  # type: ignore[misc]
        info = dict(info)
        info["options"] = {
            option_name: OptionInfo.parse(
                option_value, option_name, info["collection"] + "." + info["short_name"]
            )
            for option_name, option_value in info["options"].items()
        }
        return cls(**info)

    @classmethod
    def parse_from_ansible(
        cls,
        module_qualified_name: str,
        ansible_doc_bin_path: str = "ansible-doc",
        module_path: Path | None = None,
    ) -> ModuleInfo:
        cmd = [ansible_doc_bin_path, "-j", "-t", "module"]
        if module_path is not None:
            cmd.extend(["-M", str(module_path)])
        cmd.append(module_qualified_name)

        info_proc = subprocess.run(cmd, capture_output=True)
        response = json.loads(info_proc.stdout)
        info = response[module_qualified_name]

        doc = info["doc"]
        return cls(
            collection=doc["collection"],
            short_name=doc["module"],
            author=doc["author"],
            description=doc["description"],
            short_description=doc["short_description"],
            has_action=doc["has_action"],
            notes=doc.get("notes", []) or [],
            requirements=doc.get("requirements", []),
            attributes=doc.get("attributes", {}),
            options={
                option_name: OptionInfo.parse(
                    option_value,
                    option_name,
                    doc["collection"] + "." + doc["module"],
                )
                for option_name, option_value in doc.get("options", {}).items()
            },
            metadata=info["metadata"],
            returns=info.get("return"),
            examples=info["examples"],
        )


class ModuleKnowledgeBase:
    def __init__(self, modules: dict[str, ModuleInfo]) -> None:
        self.modules = modules
        self._unqualified_to_qualified_names: dict[str, list[str]] = defaultdict(list)
        for qualname, mod in self.modules.items():
            self._unqualified_to_qualified_names[mod.short_name].append(qualname)

    @classmethod
    def init_from_ansible_docs(
        cls, ansible_doc_bin_path: str = "ansible-doc", module_path: Path | None = None
    ) -> ModuleKnowledgeBase:
        run_args = [ansible_doc_bin_path, "-j", "-l", "-t", "module"]
        if module_path is not None:
            run_args.extend(["-M", str(module_path)])

        all_modules_resp = subprocess.run(run_args, capture_output=True).stdout
        all_module_names = json.loads(all_modules_resp).keys()

        modules: dict[str, ModuleInfo] = {}
        for mod in rich.progress.track(
            all_module_names, description=f"Scanning {len(all_module_names)} modules"
        ):
            modules[mod] = ModuleInfo.parse_from_ansible(
                mod, ansible_doc_bin_path, module_path
            )

        return cls(modules)

    def dump(self, slim: bool = True) -> dict[str, Any]:
        return {
            mod_name: asdict(
                mod_info,
                recurse=True,
                value_serializer=_slim_dump_converter if slim else None,
                filter=_slim_dump_filter if slim else None,
            )
            for mod_name, mod_info in self.modules.items()
        }

    def dump_to_file(self, file_path: Path, slim: bool = True) -> None:
        with file_path.open("wt") as f:
            json.dump(self.dump(slim), f, sort_keys=True, indent=2)

    @classmethod
    def load(cls, info: dict[str, Any]) -> ModuleKnowledgeBase:  # type: ignore[misc]
        return cls({name: ModuleInfo.load(modinfo) for name, modinfo in info.items()})

    @classmethod
    def load_from_file(cls, file_path: Path) -> ModuleKnowledgeBase:
        with file_path.open("rt") as f:
            return cls.load(json.load(f))

    def is_qualified_module_name(self, name: str) -> bool:
        return name in self.modules

    def get_qualified_module_names(self, name: str) -> list[str]:
        return self._unqualified_to_qualified_names.get(name, [])

    def get_best_matching_qualname(self, name: str, options: list[str]) -> list[str]:
        candidates = [
            self.modules[mod] for mod in self.get_qualified_module_names(name)
        ]
        if not candidates:
            return []

        # Rank by how many of the used options are supported by the module
        def calc_overlap(mod: ModuleInfo) -> int:
            return len(set(options) & mod.all_option_names)

        candidates_scored = [(cand, calc_overlap(cand)) for cand in candidates]
        highest_score = max(score for _, score in candidates_scored)

        return [
            cand.qualified_name
            for cand, score in candidates_scored
            if score == highest_score
        ]


def _slim_dump_filter(field: Attribute[Any], value: Any) -> bool:
    return value is not None


def _slim_dump_converter(inst: Any, field: Attribute[Any] | None, value: Any) -> Any:
    if field is None:
        return value

    if isinstance(inst, ModuleInfo):
        if field.name == "examples":
            return ""
        if field.name in ("notes", "requirements"):
            return []
        if field.name == "returns" and value is not None:
            return {
                ret_name: {
                    k: v
                    for k, v in ret_desc.items()
                    if k not in ("description", "sample")
                }
                for ret_name, ret_desc in value.items()
            }

    if field.name == "description":
        if isinstance(value, list):
            return []
        if isinstance(value, str):
            return ""

    return value
