# pyright: reportUnusedFunction = false

from __future__ import annotations

from textwrap import dedent

import ansible.parsing.dataloader
import pytest

from scansible.representations.structural import Block, ExtractionContext, Task


def _parse_yaml_dict(yaml_content: str) -> dict[str, object]:
    loader = ansible.parsing.dataloader.DataLoader()
    result = loader.load(data=dedent(yaml_content))
    assert isinstance(result, dict)
    return result


def describe_extracting_blocks() -> None:
    def extracts_standard_blocks() -> None:
        yaml = """
            block:
              - name: test
                file: {}
              - name: test2
                file: {}
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        assert isinstance(result.block[0], Task)
        assert isinstance(result.block[1], Task)
        assert result.block[0].name == "test"
        assert result.block[1].name == "test2"

    def extracts_blocks_with_rescue_and_always() -> None:
        yaml = """
            block:
              - name: test
                file: {}
            rescue:
              - name: test2
                file: {}
            always:
              - name: test3
                file: {}
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 1
        assert len(result.rescue) == 1
        assert len(result.always) == 1
        assert isinstance(result.block[0], Task)
        assert isinstance(result.rescue[0], Task)
        assert isinstance(result.always[0], Task)
        assert result.block[0].name == "test"
        assert result.rescue[0].name == "test2"
        assert result.always[0].name == "test3"

    def extracts_nested_blocks() -> None:
        yaml = """
            block:
              - name: test
                file: {}
              - block:
                  - name: test
                    file: {}
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        assert isinstance(result.block[0], Task)
        assert isinstance(result.block[1], Block)
        assert result.block[0].name == "test"
        assert len(result.block[1].block) == 1
        assert isinstance(result.block[1].block[0], Task)
        assert result.block[1].block[0].name == "test"

    def does_not_eagerly_load_import_tasks() -> None:
        yaml = """
            block:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 1
        assert isinstance(result.block[0], Task)
        assert result.block[0].action == "import_tasks"

    def rejects_non_blocks() -> None:
        yaml = """
            import_tasks: test
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

    def rejects_blocks_without_block() -> None:
        yaml = """
            rescue:
                - file: {}
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)

    def rejects_rescue_with_empty_block() -> None:
        yaml = """
            block: []
            rescue:
                - file: {}
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(_parse_yaml_dict(yaml), context=ctx)
