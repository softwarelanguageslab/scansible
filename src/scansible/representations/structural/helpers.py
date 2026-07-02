"""Helpers for structural model extraction."""

from __future__ import annotations

from typing import NoReturn, Protocol, cast, override

import io
import os.path
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from ansible.parsing.yaml.objects import AnsibleUnicode

from scansible.types import VaultValue

from . import ansible_types as ans


class FatalError(Exception):
    """Fatal error to stop all extraction."""

    pass


class ProjectPath:
    """
    Represents a path in a project, storing the project root path and the
    relative path to a file or directory in the project.
    """

    #: The project's root path. Must be a directory.
    root: Path
    #: Path to the content, relative to the root path.
    relative: Path

    def __init__(self, root_path: Path, file_path: Path | str) -> None:
        assert root_path.is_absolute()
        assert root_path.is_dir()
        self.root = root_path

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if file_path.is_absolute():
            self.relative = Path(os.path.relpath(file_path, root_path))
        else:
            self.relative = file_path

    @override
    def __str__(self) -> str:
        return str(self.absolute)

    @classmethod
    def from_root(cls, root_path: Path) -> ProjectPath:
        """
        Construct a ProjectPath instance for the project root.
        If given a file, will set the root the the parent of the file.

        :param      root_path:  The root path to the project.
        :type       root_path:  Path
        """
        if root_path.is_file():
            return cls(root_path.parent, root_path.name)
        return cls(root_path, ".")

    def join(self, other: Path | str) -> ProjectPath:
        """
        Join the current path with another path.

        :raises     AssertionError:  When the two project paths have different roots.
        """
        if isinstance(other, str):
            other = Path(other)

        return ProjectPath(self.root, self.relative / other)

    @property
    def absolute(self) -> Path:
        """The absolute path to the content."""
        return (self.root / self.relative).resolve()


def parse_file(path: ProjectPath) -> object:
    """Parse a YAML file using Ansible's parser."""
    loader = ans.DataLoader()
    return loader.load_from_file(str(path.absolute))


def validate_ansible_object(obj: ans.FieldAttributeBase) -> None:
    """Validate and normalise the given Ansible object.

    Uses Ansible's own validators. Normalises the object by setting default
    values for attributes that don't have values, or by normalising the values
    of certain attributes (e.g. normalising to a list when a value can be an
    atomic string or a list of strings).
    """

    # We have to reimplement Ansible's logic because it eagerly templates certain
    # expressions. We don't want that.
    templar = ans.Templar(ans.DataLoader())
    for name, attribute in obj.fattributes.items():
        value = cast(object, getattr(obj, name))
        if value is None:
            continue
        if attribute.isa == "class":
            assert isinstance(value, ans.FieldAttributeBase)
            validate_ansible_object(value)
            continue

        # We need to ensure we don't retrieve the validated value if the
        # original value is an expression. Ansible usually eagerly evaluates
        # those, we don't. We only care when it's a string, to prevent Ansible
        # from attempting to e.g. convert an expression into a boolean. If it's
        # a list containing expressions and Ansible wants to convert it to a
        # boolean, there's something wrong anyway.
        if isinstance(value, str) and templar.is_template(value):
            continue

        # templar argument is only used when attribute.isa is a class, which we
        # handle specially above.
        try:
            validated_value = obj.get_validated_value(name, attribute, value, None)
        except (TypeError, ValueError) as e:
            # Re-raise these errors like Ansible's base post_validate does.
            raise ans.AnsibleParserError(
                f"the field '{name}' has an invalid value ({value}), and could not be converted to an {attribute.isa}. The error was: {e}",
                obj=obj.get_ds(),
                orig_exc=e,
            )
        setattr(obj, name, validated_value)


def find_file(dir_path: ProjectPath, file_name: str) -> ProjectPath | None:
    """
    Find a YAML file in a project directory, regardless of file extension.

    :raises     AssertionError:  When multiple files were found.
    """
    # TODO: Use `SourceFileMap`?
    loader = ans.DataLoader()
    # DataLoader.find_vars_files is misnamed.
    found_paths = loader.find_vars_files(
        str(dir_path.absolute), file_name, allow_dir=False
    )
    # found_paths should always have at most one element, since it can only have
    # multiple elements when allow_dir=True

    if not found_paths:
        return None

    found_path = found_paths[0]
    return dir_path.join(
        found_path.decode("utf-8") if isinstance(found_path, bytes) else found_path
    )


def find_all_files(dir_path: ProjectPath) -> list[ProjectPath]:
    """Recursively find all YAML files in a project directory."""
    results: list[ProjectPath] = []
    for child in dir_path.absolute.iterdir():
        child_path = dir_path.join(child)
        if child.is_symlink():
            continue
        if child.is_file() and child.suffix in ans.C.YAML_FILENAME_EXTENSIONS:
            results.append(child_path)
        elif child.is_dir():
            try:
                results.extend(find_all_files(child_path))
            except RecursionError:
                print(child)
                # TODO: Why can this spin in an infinite loop??
                pass

    return results


@contextmanager
def capture_output() -> Iterator[io.StringIO]:
    """Context manager which, while active, captures all printed output.

    Useful to capture Ansible logs that otherwise get printed to the terminal.
    The captured output will be available as the variable in the `with`
    statement.

    Example:
      with capture_output() as output:
        print("hello world")
        sys.stderr.write('test\n')
      output.getvalue()  # hello world\ntest\n
    """
    buffer = io.StringIO()
    with ExitStack() as stack:
        _ = stack.enter_context(redirect_stderr(buffer))
        _ = stack.enter_context(redirect_stdout(buffer))
        yield buffer


class _Intercepter(Protocol):
    def __call__(self, *_args: object, **_kwargs: object) -> NoReturn: ...


@contextmanager
def prevent_undesired_operations() -> Iterator[None]:
    """
    Context manager which, while active, blocks Ansible from performing
    undesired operations such as evaluating template expressions or eagerly
    loading included files.
    """
    from ansible.playbook import helpers
    from ansible.template import Templar

    old_load_list_of_tasks = helpers.load_list_of_tasks
    old_templar_do_template = Templar.do_template
    old_templar_template = Templar.template

    def raise_if_called(name: str) -> _Intercepter:
        def raiser(*_args: object, **_kwargs: object) -> NoReturn:
            raise FatalError(f"{name} was called when it was not supposed to be called")

        return raiser

    helpers.load_list_of_tasks = raise_if_called("load_list_of_tasks")
    Templar.do_template = raise_if_called("Templar.do_template")
    Templar.template = raise_if_called("Templar.template")

    try:
        yield
    finally:
        helpers.load_list_of_tasks = old_load_list_of_tasks
        Templar.do_template = old_templar_do_template
        Templar.template = old_templar_template


def convert_ansible_values(obj: object) -> object:
    # FIXME: This is a hack, we should instead apply systematic coercion.
    if isinstance(obj, ans.AnsibleVaultEncryptedUnicode):
        return VaultValue(data=obj._ciphertext, ansible_pos=obj.ansible_pos)
    if isinstance(obj, ans.AnsibleBaseYAMLObject):
        return obj
    if isinstance(obj, str):
        assert not isinstance(obj, AnsibleUnicode)
        ans_str = AnsibleUnicode(obj)
        ans_str.ansible_pos = getattr(
            cast(object, obj),
            "ansible_pos",
            ("unknown file", -1, -1),
        )
        return ans_str
    if isinstance(obj, Sequence):
        seq = ans.AnsibleSequence([convert_ansible_values(el) for el in obj])  # pyright: ignore[reportArgumentType]
        seq.ansible_pos = getattr(
            cast(object, obj),
            "ansible_pos",
            ("unknown file", -1, -1),
        )
        return seq
    if isinstance(obj, Mapping):
        dct = ans.AnsibleMapping({k: convert_ansible_values(v) for k, v in obj.items()})  # pyright: ignore[reportUnknownVariableType]
        dct.ansible_pos = getattr(
            cast(object, obj),
            "ansible_pos",
            ("unknown file", -1, -1),
        )
        return dct
    return obj
