import pytest

from scansible.models.edges import DEF, USE, ORDER, ORDER_TRANS
from scansible.models.graph import Graph
from scansible.models.nodes import Expression, IntermediateValue, Task, Variable

from graph_matchers import assert_graphs_match, create_graph


def describe_assert_graphs_match() -> None:

    def should_match_empty_graphs() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_with_name() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test2', role_version='1.0.0')

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_with_version() -> None:
        g1 = Graph(role_name='test', role_version='1.0.1')
        g2 = Graph(role_name='test', role_version='1.0.0')

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_with_nonempty() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='hello', version=1))

        assert_graphs_match(g1, g2)

    def should_match_standard_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='hello', version=1))

        assert_graphs_match(g1, g2)

    def should_match_multiple_standard_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g1.add_node(Variable(name='world', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='hello', version=1))
        g2.add_node(Variable(name='world', version=1))

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Not implemented')
    def should_match_ivs() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(IntermediateValue(identifier=0))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(IntermediateValue(identifier=1))

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_standard_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='world', version=1))

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_mixed_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(IntermediateValue(identifier=0))

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_missing_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='hello', version=1))
        g2.add_node(Variable(name='world', version=1))

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_extra_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g1.add_node(Variable(name='hello', version=1))
        g1.add_node(Variable(name='world', version=1))
        g2 = Graph(role_name='test', role_version='1.0.0')
        g2.add_node(Variable(name='hello', version=1))

        assert_graphs_match(g1, g2)

    def should_match_edges() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        v3 = Variable(name='world', version=1)
        v4 = Variable(name='world', version=1)
        v5 = Variable(name='!', version=1)
        v6 = Variable(name='!', version=1)
        g1.add_nodes_from([v1, v3, v5])
        g2.add_nodes_from([v2, v4, v6])
        g1.add_edge(v1, v3, DEF)
        g1.add_edge(v3, v5, DEF)
        g2.add_edge(v2, v4, DEF)
        g2.add_edge(v4, v6, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_extra_edges() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        v3 = Variable(name='world', version=1)
        v4 = Variable(name='world', version=1)
        g1.add_nodes_from([v1, v3])
        g2.add_nodes_from([v2, v4])
        g1.add_edge(v1, v3, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_missing_edges() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        v3 = Variable(name='world', version=1)
        v4 = Variable(name='world', version=1)
        g1.add_nodes_from([v1, v3])
        g2.add_nodes_from([v2, v4])
        g2.add_edge(v2, v4, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_edge_direction() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        v3 = Variable(name='world', version=1)
        v4 = Variable(name='world', version=1)
        g1.add_nodes_from([v1, v3])
        g2.add_nodes_from([v2, v4])
        g1.add_edge(v1, v3, DEF)
        g2.add_edge(v4, v2, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_edge_data() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        t1 = Task(name='hello', action='world')
        t2 = Task(name='hello', action='world')
        t3 = Task(name='hello', action='world')
        t4 = Task(name='hello', action='world')
        g1.add_nodes_from([t1, t3])
        g2.add_nodes_from([t2, t4])
        g1.add_edge(t1, t3, ORDER)
        g2.add_edge(t2, t4, ORDER_TRANS)

        assert_graphs_match(g1, g2)

    def should_match_ivs_with_edges() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        i1 = IntermediateValue(identifier=0)
        i2 = IntermediateValue(identifier=0)
        g1.add_nodes_from([v1, i1])
        g2.add_nodes_from([v2, i2])
        g1.add_edge(v1, i1, DEF)
        g2.add_edge(v2, i2, DEF)

        assert_graphs_match(g1, g2)

    def should_match_ivs_with_edges_and_diff_ids() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        i1 = IntermediateValue(identifier=0)
        i2 = IntermediateValue(identifier=1)
        g1.add_nodes_from([v1, i1])
        g2.add_nodes_from([v2, i2])
        g1.add_edge(v1, i1, DEF)
        g2.add_edge(v2, i2, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_ivs() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        i1 = IntermediateValue(identifier=0)
        i2 = IntermediateValue(identifier=1)
        g1.add_nodes_from([v1, i1])
        g2.add_nodes_from([v2, i2])
        g1.add_edge(i1, v1, DEF)
        g2.add_edge(v2, i2, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_extra_ivs() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        i1 = IntermediateValue(identifier=0)
        i2 = IntermediateValue(identifier=1)
        i3 = IntermediateValue(identifier=2)
        g1.add_nodes_from([v1, i1, i3])
        g2.add_nodes_from([v2, i2])
        g1.add_edge(v1, i1, DEF)
        g1.add_edge(v1, i3, DEF)
        g2.add_edge(v2, i2, DEF)

        assert_graphs_match(g1, g2)

    @pytest.mark.xfail(strict=True, reason='Should fail')
    def should_mismatch_missing_ivs() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        v1 = Variable(name='hello', version=1)
        v2 = Variable(name='hello', version=1)
        i1 = IntermediateValue(identifier=0)
        i2 = IntermediateValue(identifier=1)
        i3 = IntermediateValue(identifier=2)
        g1.add_nodes_from([v1, i1])
        g2.add_nodes_from([v2, i2, i3])
        g1.add_edge(v1, i1, DEF)
        g2.add_edge(v2, i3, DEF)
        g2.add_edge(v2, i2, DEF)

        assert_graphs_match(g1, g2)

    def should_respect_order_of_duplicate_nodes() -> None:
        g1 = Graph(role_name='test', role_version='1.0.0')
        g2 = Graph(role_name='test', role_version='1.0.0')
        e1 = Expression(expr='x')
        e2 = Expression(expr='x')
        e3 = Expression(expr='x')
        e4 = Expression(expr='x')
        v1 = Variable(name='a', version=0)
        v2 = Variable(name='a', version=0)
        v3 = Variable(name='a', version=1)
        v4 = Variable(name='a', version=1)
        g1.add_nodes_from([e1, v1, e3, v3])
        g2.add_nodes_from([e2, v2, e4, v4])
        g1.add_edge(e1, v1, DEF)
        g1.add_edge(e3, v3, DEF)
        g2.add_edge(e2, v2, DEF)
        g2.add_edge(e4, v4, DEF)

        assert_graphs_match(g1, g2)


def describe_create_graph() -> None:

    def should_create_empty_graph() -> None:
        g1 = create_graph({}, [])
        g2 = Graph(role_name='test_role', role_version='test_version')

        assert_graphs_match(g1, g2)

    def should_create_empty_graph_with_name_and_version() -> None:
        g1 = create_graph({}, [], role_name='a', role_version='b')
        g2 = Graph(role_name='a', role_version='b')

        assert_graphs_match(g1, g2)

    def should_create_graph_with_nodes() -> None:
        g1 = create_graph({
            'a': Variable(name='a', version=1),
            'b': Variable(name='b', version=1),
        }, [])
        g2 = Graph(role_name='test_role', role_version='test_version')
        g2.add_nodes_from([Variable(name='a', version=1), Variable(name='b', version=1)])

        assert_graphs_match(g1, g2)

    def should_create_graph_with_nodes_and_edges() -> None:
        g1 = create_graph({
            'a': Expression(expr='a'),
            'b': Variable(name='b', version=1),
            'c': IntermediateValue(identifier=1)
        }, [
            ('b', 'a', USE),
            ('a', 'c', DEF)
        ])
        g2 = Graph(role_name='test_role', role_version='test_version')
        a = Expression(expr='a')
        b = Variable(name='b', version=1)
        c = IntermediateValue(identifier=1)
        g2.add_nodes_from([a, b, c])
        g2.add_edge(b, a, USE)
        g2.add_edge(a, c, DEF)

        assert_graphs_match(g1, g2)
