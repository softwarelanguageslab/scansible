import pytest

from scansible.extractor.var_context import ScopeLevel, VarContext
from scansible.models.edges import DEF, USE
from scansible.models.nodes import Literal, Variable, Expression, IntermediateValue
from scansible.models.graph import Graph

from graph_matchers import assert_graphs_match, create_graph

from scansible.io.neo4j import dump_graph

def describe_unmodified() -> None:

    @pytest.mark.parametrize('expr, type', [
        ('hello', 'str'),
        ('1', 'str'),
        ('True', 'str'),
        ('yes', 'str')
    ])
    def should_extract_literal(expr: str, type: str, g: Graph) -> None:
        ctx = VarContext()

        ctx.evaluate_template(expr, g, False)
        ln = next(iter(g))

        assert_graphs_match(g, create_graph({
            'lit': Literal(type='str', value=expr)
        }, []))

    def should_declare_literal_variable(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('test_var', 'hello world', ScopeLevel.PLAY_VARS)

        assert_graphs_match(g, create_graph({}, []))

    def should_extract_variables(g: Graph) -> None:
        ctx = VarContext()

        ctx.evaluate_template('hello {{ target }}', g, False)

        assert_graphs_match(g, create_graph({
            'var': Variable(name='target', version=0),
            'expr': Expression(expr='hello {{ target }}'),
            'iv': IntermediateValue(identifier=0)
        }, [
            ('var', 'expr', USE),
            ('expr', 'iv', DEF),
        ]))

    def should_reevaluate_template_literal(g: Graph) -> None:
        # We don't want to deduplicate template literals yet
        ctx = VarContext()

        ctx.evaluate_template('hello world', g, False)
        ctx.evaluate_template('hello world', g, False)

        assert_graphs_match(g, create_graph({
            'lit1': Literal(type='str', value='hello world'),
            'lit2': Literal(type='str', value='hello world')
        }, []))

    def should_not_reevaluate_variables(g: Graph) -> None:
        # We don't want to deduplicate template literals yet
        ctx = VarContext()

        ctx.evaluate_template('hello {{ target }}', g, False)
        ctx.evaluate_template('hello {{ target }}', g, False)

        assert_graphs_match(g, create_graph({
            'target': Variable(name='target', version=0),
            'expression': Expression(expr='hello {{ target }}'),
            'iv': IntermediateValue(identifier=1)
        }, [
            ('target', 'expression', USE),
            ('expression', 'iv', DEF)
        ]))

    def should_extract_variable_definition(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('msg', 'hello {{ target }}', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ msg }}', g, False)

        assert_graphs_match(g, create_graph({
            'target': Variable(name='target', version=0),
            'msg': Variable(name='msg', version=0),
            'e1': Expression(expr='hello {{ target }}'),
            'e2': Expression(expr='{{ msg }}'),
            'iv1': IntermediateValue(identifier=1),
            'iv2': IntermediateValue(identifier=2),
        }, [
            ('target', 'e1', USE),
            ('e1', 'iv1', DEF),
            ('iv1', 'msg', DEF),
            ('msg', 'e2', USE),
            ('e2', 'iv2', DEF)
        ]))

    @pytest.mark.parametrize('expr', [
        '{{ "/etc/tzinfo" | basename }}',
        '{{ lookup("indexed_items", [1,2,3]) }}',
        '{{ [1,2,3] | first }}'
    ])
    def should_not_reevaluate_static_templates(expr: str, g: Graph) -> None:
        ctx = VarContext()

        ctx.evaluate_template(expr, g, False)
        ctx.evaluate_template(expr, g, False)

        assert_graphs_match(g, create_graph({
            'e': Expression(expr=expr),
            'iv': IntermediateValue(identifier=1),
        }, [
            ('e', 'iv', DEF)
        ]))


def describe_modified() -> None:

    @pytest.mark.parametrize('expr', [
        'The time is {{ now() }}',
        '{{ "/etc/tzinfo" is file }}',
        '{{ lookup("pipe", "echo Hello World") }}',
        '{{ [1,2,3] | random }}'
    ])
    def should_reevaluate_dynamic_templates(expr: str, g: Graph) -> None:
        ctx = VarContext()

        ctx.evaluate_template(expr, g, False)
        ctx.evaluate_template(expr, g, False)

        assert_graphs_match(g, create_graph({
            'e': Expression(expr=expr),
            'iv1': IntermediateValue(identifier=1),
            'iv2': IntermediateValue(identifier=2),
        }, [
            ('e', 'iv1', DEF),
            ('e', 'iv2', DEF)
        ]))

    def should_reevaluate_when_variable_changed(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', 'hello', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ a }} world', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', 'hi', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('{{ a }} world', g, False)

        assert_graphs_match(g, create_graph({
            'a1': Variable(name='a', version=0),
            'l1': Literal(type='str', value='hello'),
            'e1': Expression(expr='{{ a }} world'),
            'a2': Variable(name='a', version=1),
            'l2': Literal(type='str', value='hi'),
            'e2': Expression(expr='{{ a }} world'),
            'iv1': IntermediateValue(identifier=1),
            'iv2': IntermediateValue(identifier=2),
        }, [
            ('l1', 'a1', DEF),
            ('a1', 'e1', USE),
            ('e1', 'iv1', DEF),
            ('l2', 'a2', DEF),
            ('a2', 'e2', USE),
            ('e2', 'iv2', DEF),
        ]))

    def should_reevaluate_when_variable_dynamic(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('when', '{{ now() }}', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('The time is {{ when }}', g, False)
        ctx.evaluate_template('The time is {{ when }}', g, False)

        assert_graphs_match(g, create_graph({
            'e1': Expression(expr='{{ now() }}'),
            'iv1': IntermediateValue(identifier=1),
            'when1': Variable(name='when', version=0),
            'e2': Expression(expr='The time is {{ when }}', node_id=-2),  # Specify node ID to ensure proper match with duplicates
            'iv2': IntermediateValue(identifier=2),
            'e3': Expression(expr='The time is {{ when }}', node_id=-1),
            'iv3': IntermediateValue(identifier=3),
            'when2': Variable(name='when', version=1),
            'iv4': IntermediateValue(identifier=4),
        }, [
            ('e1', 'iv1', DEF),
            ('iv1', 'when1', DEF),
            ('when1', 'e2', USE),
            ('e2', 'iv2', DEF),
            ('e1', 'iv3', DEF),
            ('iv3', 'when2', DEF),
            ('when2', 'e3', USE),
            ('e3', 'iv4', DEF),
        ]))

    def should_reevaluate_with_deeply_nested_expressions(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', 'hello', ScopeLevel.PLAY_VARS)
        ctx.register_variable('b', '{{ a }} world', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ b }}!', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', 'hi', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('{{ b }}!', g, False)

        assert_graphs_match(g, create_graph({
            'a1': Variable(name='a', version=0),
            'l1': Literal(type='str', value='hello'),
            'b1': Variable(name='b', version=0),
            'e1': Expression(expr='{{ a }} world'),
            'i1': IntermediateValue(identifier=1),
            'e2': Expression(expr='{{ b }}!'),
            'i2': IntermediateValue(identifier=2),
            'a2': Variable(name='a', version=1),
            'l2': Literal(type='str', value='hi'),
            'b2': Variable(name='b', version=1),
            'e3': Expression(expr='{{ a }} world'),
            'i3': IntermediateValue(identifier=3),
            'e4': Expression(expr='{{ b }}!'),
            'i4': IntermediateValue(identifier=4),
        }, [
            ('l1', 'a1', DEF),
            ('a1', 'e1', USE),
            ('e1', 'i1', DEF),
            ('i1', 'b1', DEF),
            ('b1', 'e2', USE),
            ('e2', 'i2', DEF),
            ('l2', 'a2', DEF),
            ('a2', 'e3', USE),
            ('e3', 'i3', DEF),
            ('i3', 'b2', DEF),
            ('b2', 'e4', USE),
            ('e4', 'i4', DEF),
        ]))

    def should_reevaluate_only_one_var(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', 'hello', ScopeLevel.PLAY_VARS)
        ctx.register_variable('b', 'world', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ a }} {{ b }}!', g, False)
        ctx.register_variable('a', 'hi', ScopeLevel.PLAY_VARS_PROMPT)
        ctx.evaluate_template('{{ a }} {{ b }}!', g, False)

        assert_graphs_match(g, create_graph({
            'a1': Variable(name='a', version=0),
            'l1': Literal(type='str', value='hello'),
            'b': Variable(name='b', version=0),
            'l2': Literal(type='str', value='world'),
            'e1': Expression(expr='{{ a }} {{ b }}!'),
            'i1': IntermediateValue(identifier=1),
            'a2': Variable(name='a', version=1),
            'l3': Literal(type='str', value='hi'),
            'e2': Expression(expr='{{ a }} {{ b }}!'),
            'i2': IntermediateValue(identifier=2),
        }, [
            ('l1', 'a1', DEF),
            ('l2', 'b', DEF),
            ('a1', 'e1', USE),
            ('b', 'e1', USE),
            ('e1', 'i1', DEF),
            ('l3', 'a2', DEF),
            ('a2', 'e2', USE),
            ('b', 'e2', USE),
            ('e2', 'i2', DEF)
        ]))

def describe_scoping() -> None:

    def should_use_most_specific_scope(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', '2', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('2 {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'aouter': Variable(name='a', version=0),
            '1': Literal(type='str', value='1'),
            'e1': Expression(expr='1 {{ a }}'),
            'iv1': IntermediateValue(identifier=1),
            'ainner': Variable(name='a', version=1),
            '2': Literal(type='str', value='2'),
            'e2': Expression(expr='2 {{ a }}'),
            'iv2': IntermediateValue(identifier=2),
        }, [
            ('1', 'aouter', DEF),
            ('aouter', 'e1', USE),
            ('e1', 'iv1', DEF),
            ('2', 'ainner', DEF),
            ('ainner', 'e2', USE),
            ('e2', 'iv2', DEF),
        ]))

    def should_override_root_scope_variables(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', '2', ScopeLevel.SET_FACTS_REGISTERED)
        ctx.evaluate_template('{{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'ainner': Variable(name='a', version=1),
            '2': Literal(type='str', value='2'),
            'e': Expression(expr='{{ a }}'),
            'iv': IntermediateValue(identifier=1),
        }, [
            ('2', 'ainner', DEF),
            ('ainner', 'e', USE),
            ('e', 'iv', DEF),
        ]))

    def should_reuse_prev_outer_template_in_inner(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.evaluate_template('1 {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'aouter': Variable(name='a', version=0),
            '1': Literal(type='str', value='1'),
            'e1': Expression(expr='1 {{ a }}'),
            'iv1': IntermediateValue(identifier=1),
        }, [
            ('1', 'aouter', DEF),
            ('aouter', 'e1', USE),
            ('e1', 'iv1', DEF),
        ]))

    def should_reuse_prev_outer_template_in_outer(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', '2', ScopeLevel.ELEMENT_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'aouter': Variable(name='a', version=0),
            '1': Literal(type='str', value='1'),
            'e1': Expression(expr='1 {{ a }}'),
            'iv1': IntermediateValue(identifier=1),
        }, [
            ('1', 'aouter', DEF),
            ('aouter', 'e1', USE),
            ('e1', 'iv1', DEF),
        ]))

    def should_hoist_template(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('c', 'c', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('1 {{ a }}', g, False)
            ctx.register_variable('a', '2', ScopeLevel.ELEMENT_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'aouter': Variable(name='a', version=0),
            '1': Literal(type='str', value='1'),
            'e1': Expression(expr='1 {{ a }}'),
            'iv1': IntermediateValue(identifier=1),
        }, [
            ('1', 'aouter', DEF),
            ('aouter', 'e1', USE),
            ('e1', 'iv1', DEF),
        ]))

    def should_not_hoist_template_if_overridden(g: Graph) -> None:
        ctx = VarContext()

        # Difference to 'should_use_most_specific_scope': Same template here,
        # different template there
        ctx.register_variable('a', '1', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('1 {{ a }}', g, False)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', '2', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('1 {{ a }}', g, False)
        ctx.evaluate_template('1 {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'aouter': Variable(name='a', version=0),
            '1': Literal(type='str', value='1'),
            'e1': Expression(expr='1 {{ a }}'),
            'iv1': IntermediateValue(identifier=1),
            'ainner': Variable(name='a', version=1),
            '2': Literal(type='str', value='2'),
            'e2': Expression(expr='1 {{ a }}'),
            'iv2': IntermediateValue(identifier=2),
        }, [
            ('1', 'aouter', DEF),
            ('aouter', 'e1', USE),
            ('e1', 'iv1', DEF),
            ('2', 'ainner', DEF),
            ('ainner', 'e2', USE),
            ('e2', 'iv2', DEF),
        ]))

    def should_evaluate_var_into_template_scope(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '{{ b }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('b', '1', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('{{ a }}', g, False)
        ctx.register_variable('b', '2', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'ai': Variable(name='a', version=0),
            'aei': Expression(expr='{{ b }}'),
            'aeiv': IntermediateValue(identifier=0),
            'binner': Variable(name='b', version=0),
            'bil': Literal(type='str', value='1'),
            'ei': Expression(expr='{{ a }}'),
            'eiv': IntermediateValue(identifier=1),
            'bouter': Variable(name='b', version=0),
            'bol': Literal(type='str', value='2'),
            'eo': Expression(expr='{{ a }}'),
            'eov': IntermediateValue(identifier=2),
            'ao': Variable(name='a', version=0),
            'aeo': Expression(expr='{{ b }}'),
            'aeov': IntermediateValue(identifier=2),
        }, [
            ('aei', 'aeiv', DEF),
            ('aeiv', 'ai', DEF),
            ('bil', 'binner', DEF),
            ('ei', 'eiv', DEF),
            ('ai', 'ei', USE),
            ('binner', 'aei', USE),
            ('eo', 'eov', DEF),
            ('ao', 'eo', USE),
            ('aeo', 'aeov', DEF),
            ('aeov', 'ao', DEF),
            ('bouter', 'aeo', USE),
            ('bol', 'bouter', DEF),
        ]))

    def should_reuse_nested_templates(g: Graph) -> None:
        ctx = VarContext()

        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('a', '{{ "hello" | reverse }}', ScopeLevel.ELEMENT_VARS)
            ctx.register_variable('b', '{{ c | reverse }}', ScopeLevel.ELEMENT_VARS)
            ctx.register_variable('c', 'world', ScopeLevel.ELEMENT_VARS)
            ctx.evaluate_template('{{ b }} {{ a }}', g, False)
        ctx.register_variable('a', '{{ "hello" | reverse }}', ScopeLevel.PLAY_VARS)
        ctx.evaluate_template('{{ b }} {{ a }}', g, False)

        assert_graphs_match(g, create_graph({
            'c': Variable(name='c', version=0),
            'cl': Literal(type='str', value='world'),

            'bie': Expression(expr='{{ c | reverse }}'),
            'biv': IntermediateValue(identifier=0),
            'binner': Variable(name='b', version=0),

            'ae': Expression(expr='{{ "hello" | reverse }}'),
            'aiv': IntermediateValue(identifier=1),
            'ai': Variable(name='a', version=0),

            'ie': Expression(expr='{{ b }} {{ a }}'),
            'iev': IntermediateValue(identifier=2),

            'bouter': Variable(name='b', version=0),

            'ao': Variable(name='a', version=0),

            'oe': Expression(expr='{{ b }} {{ a }}'),
            'oev': IntermediateValue(identifier=3),
        }, [
            ('cl', 'c', DEF),

            ('c', 'bie', USE),
            ('bie', 'biv', DEF),
            ('biv', 'binner', DEF),

            ('ae', 'aiv', DEF),
            ('aiv', 'ai', DEF),

            ('binner', 'ie', USE),
            ('ai', 'ie', USE),
            ('ie', 'iev', DEF),

            ('aiv', 'ao', DEF),

            ('bouter', 'oe', USE),
            ('ao', 'oe', USE),
            ('oe', 'oev', DEF),
        ]))

    def should_hoist_variable_binding(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('a', '{{ b }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('b', '1', ScopeLevel.ELEMENT_VARS)
            with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
                ctx.evaluate_template('{{ a }}', g, False)
            ctx.evaluate_template('{{ a }}', g, False)  # Should reuse above expr

        assert_graphs_match(g, create_graph({
            'a': Variable(name='a', version=0),
            'b': Variable(name='b', version=0),
            'lb': Literal(type='str', value='1'),
            'ae': Expression(expr='{{ b }}'),
            'aei': IntermediateValue(identifier=0),
            'te': Expression(expr='{{ a }}'),
            'tei': IntermediateValue(identifier=1),
        }, [
            ('lb', 'b', DEF),
            ('aei', 'a', DEF),
            ('ae', 'aei', DEF),
            ('b', 'ae', USE),
            ('a', 'te', USE),
            ('te', 'tei', DEF),
        ]))

    def should_respect_precedence_register_element(g: Graph) -> None:
        ctx = VarContext()

        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('b', '1', ScopeLevel.ELEMENT_VARS)
        vn = ctx.register_variable('b', None, ScopeLevel.SET_FACTS_REGISTERED)
        ln = Literal(type='int', value=2)
        g.add_node(ln)
        g.add_edge(ln, vn, DEF)
        ctx.evaluate_template('{{ b }}', g, False)

        assert_graphs_match(g, create_graph({
            '2': Literal(type='int', value=2),
            'b': Variable(name='b', version=0),
            'be': Expression(expr='{{ b }}'),
            'beiv': IntermediateValue(identifier=0),
        }, {
            ('2', 'b', DEF),
            ('b', 'be', USE),
            ('be', 'beiv', DEF),
        }))

    def should_respect_precedence_overriding_in_template(g: Graph) -> None:
        ctx = VarContext()

        with ctx.enter_scope(ScopeLevel.ELEMENT_VARS):
            ctx.register_variable('b', '1', ScopeLevel.ELEMENT_VARS)
            vn = ctx.register_variable('b', None, ScopeLevel.SET_FACTS_REGISTERED)
            ln = Literal(type='int', value=2)
            g.add_node(ln)
            g.add_edge(ln, vn, DEF)
            ctx.evaluate_template('{{ b }}', g, False)
        ctx.evaluate_template('{{ b }}', g, False)  # Should reuse above expr

        print(dump_graph(g))
        assert_graphs_match(g, create_graph({
            '2': Literal(type='int', value=2),
            'b': Variable(name='b', version=1),
            'be': Expression(expr='{{ b }}'),
            'beiv': IntermediateValue(identifier=0),
        }, {
            ('2', 'b', DEF),
            ('b', 'be', USE),
            ('be', 'beiv', DEF),
        }))


def describe_caching() -> None:

    def should_cache_dynamic_template_variables(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tr = ctx.evaluate_template('{{ b }}', g, False)
            tr2 = ctx.evaluate_template('{{ b }}', g, False)  # Should reuse above

        assert tr.data_node is tr2.data_node

    def should_discard_after_leaving_scope(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tr = ctx.evaluate_template('{{ b }}', g, False)
            tr2 = ctx.evaluate_template('{{ b }}', g, False)  # Should reuse above
        tr3 = ctx.evaluate_template('{{ b }}', g, False)  # Should not reuse above

        assert tr.data_node is tr2.data_node
        assert tr.data_node is not tr3.data_node

    def should_not_reuse_previous_value_of_dynamic_template_var(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        tr1 = ctx.evaluate_template('{{ b }}', g, False)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tr2 = ctx.evaluate_template('{{ b }}', g, False)
        tr3 = ctx.evaluate_template('{{ b }}', g, False)

        assert tr1.data_node is not tr2.data_node
        assert tr1.data_node is not tr3.data_node
        assert tr2.data_node is not tr3.data_node

    def should_not_cache_bare_expressions(g: Graph) -> None:
        ctx = VarContext()

        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tr1 = ctx.evaluate_template('{{ now() }}', g, False)
            tr2 = ctx.evaluate_template('{{ now() }}', g, False)

        assert tr1.data_node is not tr2.data_node

    def should_not_reuse_outer_cache(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tro1 = ctx.evaluate_template('{{ b }}', g, False)
            with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
                tri1 = ctx.evaluate_template('{{ b }}', g, False)
                tri2 = ctx.evaluate_template('{{ b }}', g, False)
            tro2 = ctx.evaluate_template('{{ b }}', g, False)

        assert tri1.data_node is tri2.data_node
        assert tro1.data_node is tro2.data_node
        assert tri1.data_node is not tro1.data_node

    def should_cache_nested_variables(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        ctx.register_variable('a', '{{ b }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            tr1 = ctx.evaluate_template('{{ a }}', g, False)
            tr2 = ctx.evaluate_template('{{ a }}', g, False)

        assert tr1.data_node is tr2.data_node

    def should_reuse_variables_in_different_expressions(g: Graph) -> None:
        ctx = VarContext()

        ctx.register_variable('b', '{{ now() }}', ScopeLevel.PLAY_VARS)
        with ctx.enter_cached_scope(ScopeLevel.ELEMENT_VARS):
            ctx.evaluate_template('{{ b + 1 }}', g, False)
            ctx.evaluate_template('{{ b + 2 }}', g, False)

        assert_graphs_match(g, create_graph({
            'b': Variable(name='b', version=0),
            'be': Expression(expr='{{ now() }}'),
            'bei': IntermediateValue(identifier=0),
            'e1': Expression(expr='{{ b + 1 }}'),
            'e2': Expression(expr='{{ b + 2 }}'),
            'ei1': IntermediateValue(identifier=1),
            'ei2': IntermediateValue(identifier=2),
        }, {
            ('be', 'bei', DEF),
            ('bei', 'b', DEF),
            ('b', 'e1', USE),
            ('b', 'e2', USE),
            ('e1', 'ei1', DEF),
            ('e2', 'ei2', DEF),
        }))
