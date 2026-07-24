# pyright: reportUnusedFunction = false

from __future__ import annotations

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]

from scansible.representations.ast import Block, ExtractionContext, Task
from scansible.representations.ast.nodes.expression import BoolLiteral, Condition


def describe_extracting_blocks():
    def extracts_standard_blocks():
        yaml = """
            block:
              - name: test
                file: {}
              - name: test2
                file: {}
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        assert isinstance(result.block[0], Task)
        assert isinstance(result.block[1], Task)
        assert result.block[0].name == "test"
        assert result.block[1].name == "test2"

    def extracts_blocks_with_rescue_and_always():
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

        result = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

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

    def extracts_nested_blocks():
        yaml = """
            block:
              - name: test
                file: {}
              - block:
                  - name: test
                    file: {}
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        c1 = result.block[0]
        c2 = result.block[1]
        assert isinstance(c1, Task)
        assert isinstance(c2, Block)
        assert c1.name == "test"
        assert len(c2.block) == 1
        assert isinstance(c2.block[0], Task)
        assert c2.block[0].name == "test"

    def extracts_block_directives():
        yaml = """
            block:
              - name: test
                file: {}
            when: some_condition
            notify: a handler
            delegate_to: otherhost
            delegate_facts: yes
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.when) == 1
        c = result.when[0]
        assert isinstance(c, Condition)
        assert c.raw == "some_condition"
        assert result.notify == ("a handler",)
        assert result.delegate_to == "otherhost"
        assert result.delegate_facts == BoolLiteral(True)

    def does_not_eagerly_load_import_tasks():
        yaml = """
            block:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 1
        c = result.block[0]
        assert isinstance(c, Task)
        assert c.action == "import_tasks"

    def rejects_non_blocks():
        yaml = """
            import_tasks: test
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_blocks_without_block():
        yaml = """
            rescue:
                - file: {}
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_rescue_with_empty_block():
        yaml = """
            block: []
            rescue:
                - file: {}
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Block.model_validate(parse_yaml_dict(yaml), context=ctx)
