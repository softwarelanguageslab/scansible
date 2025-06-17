"""Helpers for structural model extraction."""

from __future__ import annotations

import io
import os.path
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Generator, NoReturn

from . import ansible_types as ans
from . import representation as rep


class FatalError(Exception):
    """Fatal error to stop all extraction."""

    pass


class ProjectPath:
    """
    Represents a path in a project, storing the project root path and the
    relative path to a file or directory in the project.
    """

    #: The project's root path.
    root: Path
    #: Path to the content, relative to the root path.
    relative: Path

    def __init__(self, root_path: Path, file_path: Path | str) -> None:
        assert root_path.is_absolute()
        self.root = root_path

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if file_path.is_absolute():
            self.relative = Path(os.path.relpath(file_path, root_path))
        else:
            self.relative = file_path

    def __str__(self) -> str:
        return str(self.absolute)

    @classmethod
    def from_root(cls, root_path: Path) -> ProjectPath:
        """
        Construct a ProjectPath instance for the project root.

        :param      root_path:  The root path to the project.
        :type       root_path:  Path
        """
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
        value = getattr(obj, name)
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
def capture_output() -> Generator[io.StringIO, None, None]:
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
        stack.enter_context(redirect_stderr(buffer))
        stack.enter_context(redirect_stdout(buffer))
        yield buffer


@contextmanager
def prevent_undesired_operations() -> Generator[None, None, None]:
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

    def raise_if_called(name: str) -> Callable[[Any], NoReturn]:
        def raiser(*args: object, **kwargs: object) -> NoReturn:
            raise FatalError(f"{name} was called when it was not supposed to be called")

        return raiser

    helpers.load_list_of_tasks = raise_if_called("load_list_of_tasks")  # type: ignore[assignment]
    Templar.do_template = raise_if_called("Templar.do_template")  # type: ignore[assignment]
    Templar.template = raise_if_called("Templar.template")  # type: ignore[assignment]

    try:
        yield
    finally:
        helpers.load_list_of_tasks = old_load_list_of_tasks
        Templar.do_template = old_templar_do_template  # type: ignore[assignment]
        Templar.template = old_templar_template  # type: ignore[assignment]


def convert_ansible_values(obj: Any) -> Any:
    if isinstance(obj, ans.AnsibleVaultEncryptedUnicode):
        return rep.VaultValue(data=obj._ciphertext, location=obj.ansible_pos)
    if isinstance(obj, list):
        seq = ans.AnsibleSequence(
            [convert_ansible_values(el) for el in obj]  # pyright: ignore
        )
        seq.ansible_pos = getattr(
            obj,
            "ansible_pos",
            ("unknown file", -1, -1),  # pyright: ignore
        )
        return seq
    if isinstance(obj, dict):
        dct = ans.AnsibleMapping(
            {k: convert_ansible_values(v) for k, v in obj.items()}  # pyright: ignore
        )
        dct.ansible_pos = getattr(
            obj,
            "ansible_pos",
            ("unknown file", -1, -1),  # pyright: ignore
        )
        return dct
    return obj
