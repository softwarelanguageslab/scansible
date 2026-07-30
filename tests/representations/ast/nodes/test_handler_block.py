# pyright: reportUnusedFunction = false

from __future__ import annotations

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]

from scansible.representations.ast import ExtractionContext, Handler, HandlerBlock
from scansible.representations.ast.nodes.expression import BoolLiteral, Condition


def describe_extracting_handler_blocks():
    def extracts_standard_handler_blocks():
        yaml = """
            block:
              - name: test
                debug: msg=hi
                listen: a topic
              - name: test2
                debug: msg=hi
                listen: a topic
        """
        ctx = ExtractionContext(False)

        result = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        h0, h1 = result.block
        assert isinstance(h0, Handler)
        assert isinstance(h1, Handler)
        assert h0.name == "test"
        assert h1.name == "test2"
        assert h0.listen == ("a topic",)

    def extracts_handler_blocks_with_rescue_and_always():
        # Syntactically valid, even though real Ansible never executes
        # rescue/always for handler blocks -- that's a PDG-layer concern.
        yaml = """
            block:
              - name: test
                debug: msg=hi
            rescue:
              - name: test2
                debug: msg=hi
            always:
              - name: test3
                debug: msg=hi
        """
        ctx = ExtractionContext(False)

        result = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 1
        assert len(result.rescue) == 1
        assert len(result.always) == 1
        assert isinstance(result.block[0], Handler)
        assert isinstance(result.rescue[0], Handler)
        assert isinstance(result.always[0], Handler)
        assert result.block[0].name == "test"
        assert result.rescue[0].name == "test2"
        assert result.always[0].name == "test3"

    def extracts_nested_handler_blocks():
        yaml = """
            block:
              - name: test
                debug: msg=hi
              - block:
                  - name: test
                    debug: msg=hi
                    listen: a topic
        """
        ctx = ExtractionContext(False)

        result = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert len(result.block) == 2
        c1 = result.block[0]
        c2 = result.block[1]
        assert isinstance(c1, Handler)
        assert isinstance(c2, HandlerBlock)
        assert c1.name == "test"
        assert len(c2.block) == 1
        h = c2.block[0]
        assert isinstance(h, Handler)
        assert h.name == "test"
        assert h.listen == ("a topic",)

    def extracts_handler_block_directives():
        yaml = """
            block:
              - name: test
                debug: msg=hi
            when: some_condition
            notify: a handler
            delegate_to: otherhost
            delegate_facts: yes
        """
        ctx = ExtractionContext(False)

        result = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.when) == 1
        c = result.when[0]
        assert isinstance(c, Condition)
        assert c.raw == "some_condition"
        assert result.notify == ("a handler",)
        assert result.delegate_to == "otherhost"
        assert result.delegate_facts == BoolLiteral(True)

    def rejects_non_blocks():
        yaml = """
            import_tasks: test
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValueError):
            _ = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_handler_blocks_without_block():
        yaml = """
            rescue:
                - debug: msg=hi
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValueError):
            _ = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_rescue_with_empty_handler_block():
        yaml = """
            block: []
            rescue:
                - debug: msg=hi
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValueError):
            _ = HandlerBlock.model_validate(parse_yaml_dict(yaml), context=ctx)
