"""Structural model importer."""

from collections.abc import Iterable
from pathlib import Path

from voyager.models.structural.role import MultiStructuralRoleModel, StructuralRoleModel

def import_role(path: Path) -> MultiStructuralRoleModel:
    role_id = path.stem

    return MultiStructuralRoleModel.load(role_id, path)


def import_role_head(path: Path) -> StructuralRoleModel:
    msrm = import_role(path)

    return next(
            srm for srm in msrm.structural_models
            if srm.role_rev == 'HEAD')


def import_all_role_heads(path: Path) -> Iterable[StructuralRoleModel]:
    for srm_file in path.iterdir():
        if srm_file.name == 'index.yaml':
            continue
        if not srm_file.is_file():
            # Raw role, should be parsed
            yield StructuralRoleModel.create(srm_file, srm_file.name, 'test')
        elif srm_file.name.endswith('.yaml'):
            yield import_role_head(srm_file)


def parse_role(path: Path, role_id: str) -> StructuralRoleModel:
    return StructuralRoleModel.create(path, role_id, '1.0.0')
