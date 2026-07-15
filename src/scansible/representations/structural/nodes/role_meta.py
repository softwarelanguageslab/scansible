# pyright: reportUnknownVariableType = false

from __future__ import annotations

from typing import Annotated, override

from collections.abc import Mapping, Sequence

from pydantic import Field, field_validator, model_validator

from scansible.types import AnyValue
from scansible.utils import FrozenDict

from .._normalizers import Lenient, Listify, Stringify
from ..common import ExtractionContext
from ..helpers import ProjectPath, parse_file
from .base import ASTFile, ASTNode
from .directives import CommonDirectives


class Platform(ASTNode, frozen=True):
    """Represents a platform supported by a role, as denoted in the meta file."""

    #: Platform name.
    name: str
    #: Platform version.
    version: str = Field(strict=False)


class _RawPlatform(ASTNode, frozen=True):
    """Intermediate Platform representation with a list of versions."""

    #: Platform name.
    name: str
    #: Platform versions.
    versions: Annotated[
        Sequence[Annotated[str, Field(strict=False)]], Stringify, Listify
    ]

    def expand(self) -> Sequence[Platform]:
        """Expand a single raw platform instance to a flattened list of platforms."""
        return [
            Platform(name=self.name, version=version, position=self.position)
            for version in self.versions
        ]


class RoleRequirement(ASTNode, CommonDirectives, frozen=True):
    """Represents a role inclusion dependency.

    These occur in a play's `roles` directive or a role's `dependencies`, see concrete subclasses.
    """

    #: The role that is depended upon.
    role: str

    #: The role include parameters.
    params: Mapping[str, AnyValue] = Field(default_factory=FrozenDict)

    #: Delegate execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None

    #: Optional condition on when to include a dependency.
    when: Annotated[Sequence[str | bool], Listify] = Field(default_factory=tuple)

    @field_validator("role", mode="after")
    def _validate_role_name(cls, value: str) -> str:
        # Commas in role names are only allowed in meta/main.yml dependencies, and should have
        # been filtered out/converted already.
        if "," in value:
            raise ValueError(f"Invalid old-style role requirement: {value}")
        return value

    @model_validator(mode="before")
    @classmethod
    def _extract_parameters(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        valid_attr_names = cls.model_fields.keys()
        new_value = {"params": {}}
        for k, v in value.items():
            if k in valid_attr_names:
                new_value[k] = v
            else:
                new_value["params"][k] = v
        return new_value


class MetaRoleRequirement(RoleRequirement, frozen=True):
    """Represents a role dependency specified in a role's `meta/main.yml` file.

    These differ from play-level dependencies as the role can be specified with the Ansible Galaxy
    notation found in requirements.yml, and thus require specialised parsing.
    """

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, value: object) -> object:
        """Parse the AST from the raw YAML specification."""

        # Need to make sure these run in the correct order.
        value = cls._parse_from_string(value)
        value = cls._extract_role_name(value)
        return value

    @classmethod
    def _parse_from_string(cls, value: object) -> object:
        # Ansible coerces int to str here, we'll do it too.
        if isinstance(value, int):
            value = str(value)

        if not isinstance(value, str):
            return value

        # Normalize to new-style role dependency if the raw string contains a comma, otherwise to an old-style
        # dependency. Validation as per `ansible.playbook.role.requirement`.
        match value.split(","):
            case [src, version, name]:
                return {"src": src, "version": version, "name": name}
            case [src, version]:
                return {"src": src, "version": version}
            case [src]:
                return {"src": src}
            case _:
                raise ValueError(
                    f"Invalid role line: {value}. Proper format is 'src[,version[,name]]'"
                )

    @classmethod
    def _extract_role_name(cls, value: object) -> object:
        if not isinstance(value, dict) or "role" in value:
            return value

        # Omit role soure info
        new_value = {
            k: v for k, v in value.items() if k not in ("src", "version", "scm")
        }

        if "name" in value:
            new_value["role"] = value["name"]
        elif "src" in value:
            src = value["src"]
            if not isinstance(src, str):
                raise ValueError(
                    "Expected `src` in new-style role requirement to be a str"
                )

            # Extraction per ansible.playbook.role.requirement.
            name = (
                src.split("/")[-1]
                .removesuffix(".git")
                .removesuffix(".tar.gz")
                .split(",")[0]
            )
            new_value["role"] = name
        else:
            raise ValueError("Expected `src` or `name` in new-style role requirement")

        return new_value


class MetaBlock(ASTNode, frozen=True, extra="ignore"):
    """Represents a role metadata block."""

    #: Platforms supported by the role
    platforms: Annotated[Sequence[Platform], Listify] = Field(default_factory=tuple)
    #: Role dependencies
    dependencies: Annotated[Sequence[MetaRoleRequirement], Lenient] = Field(
        default_factory=tuple
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def _convert_platforms(cls, value: object) -> object:
        """Convert the platforms list into a consistent schema before validation."""

        assert isinstance(value, list)  # Should be covered by the Listify marker.
        raw_platforms = [_RawPlatform.model_validate(platform) for platform in value]
        return [
            platform
            for raw_platform in raw_platforms
            for platform in raw_platform.expand()
        ]

    @model_validator(mode="before")
    @classmethod
    def _hoist_platforms(cls, value: object) -> object:
        """Hoist `galaxy_info.platforms` to a top-level key before validation."""

        if isinstance(value, dict) and "galaxy_info" in value:
            if not isinstance(value["galaxy_info"], dict):
                raise ValueError("Expected `galaxy_info` to be a dict")
            if "platforms" in value["galaxy_info"]:
                value["platforms"] = value["galaxy_info"]["platforms"]

        return value


class MetaFile(ASTFile, frozen=True):
    """Represents a file containing role metadata."""

    #: The metadata block contained in the file.
    metablock: MetaBlock

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> MetaFile:
        return cls.model_validate(
            {"path": path.relative, "metablock": parse_file(path)}, context=context
        )
