from __future__ import annotations

from typing import Any, TypeGuard, TypeVar, cast

from collections import defaultdict

from ansible.module_utils.common.parameters import DEFAULT_TYPE_VALIDATORS
from jinja2 import nodes as jnodes
from jinja2.visitor import NodeVisitor
from loguru import logger

from scansible.utils import first
from scansible.utils.module_type_info import ModuleInfo, ModuleKnowledgeBase, OptionInfo
from scansible.utils.type_validators import ensure_not_none

from .extractor.expressions.templates import (
    ASTStringifier,
    NodeReplacerVisitor,
    TemplateExpressionAST,
)
from .extractor.expressions.var_context import extract_type_name
from .representation import (
    CompositeLiteral,
    Composition,
    Conditional,
    Def,
    DefLoopItem,
    Edge,
    Expression,
    Graph,
    Input,
    IntermediateValue,
    Keyword,
    Loop,
    Node,
    ScalarLiteral,
    Task,
    Variable,
)


def canonicalize_pdg(pdg: Graph, module_kb: ModuleKnowledgeBase) -> Graph:
    _normalize_modules(pdg, module_kb)
    _simplify_dataflow(pdg)
    _normalize_data_types(pdg, module_kb)
    _remove_unused_subgraphs(pdg)
    return pdg


def _normalize_modules(pdg: Graph, module_kb: ModuleKnowledgeBase) -> None:
    _qualify_module_names(pdg, module_kb)
    _normalize_keyword_aliases(pdg, module_kb)


def _keyword_to_option_name(keyword: str) -> str:
    keyword = keyword.removeprefix("args.")
    if keyword == "_raw_params":
        keyword = "free_form"
    return keyword


def _qualify_module_names(pdg: Graph, module_kb: ModuleKnowledgeBase) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, Task):
            continue

        if module_kb.is_qualified_module_name(node.action):
            continue

        qualnames = module_kb.get_qualified_module_names(node.action)
        if not qualnames:
            logger.warning(f"Unknown unqualified action name {node.action!r}")
            continue

        if len(qualnames) > 1:
            used_options = [
                _keyword_to_option_name(edge.keyword)
                for _, _, edge in pdg.in_edges(node, data="type")
                if isinstance(edge, Keyword)
            ]
            qualnames = module_kb.get_best_matching_qualname(node.action, used_options)

        if len(qualnames) > 1:
            logger.warning(
                f"Ambiguous unqualified action name {node.action!r}, options: {qualnames!r}"
            )
            continue

        _replace_node(pdg, node, Task(qualnames[0], node.name, location=node.location))


def _normalize_keyword_aliases(pdg: Graph, module_kb: ModuleKnowledgeBase) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, Task):
            continue

        module = module_kb.modules.get(node.action)
        if module is None:
            logger.warning(f"Could not resolve module {node.action!r}")
            continue

        for src_node, _, kw_edge in list(pdg.in_edges(node, data="type")):
            if not isinstance(kw_edge, Keyword) or not kw_edge.keyword.startswith(
                "args."
            ):
                continue

            option_name = _keyword_to_option_name(kw_edge.keyword)
            canonical_name = module.get_canonical_option_name(option_name)
            if canonical_name is None:
                logger.warning(f"Could not resolve option {node.action}.{option_name}")
                continue

            if option_name == canonical_name:
                continue

            logger.info(
                f"Normalizing {node.action}'s {option_name} to {canonical_name}"
            )
            _replace_edge(
                pdg, src_node, node, kw_edge, Keyword(f"args.{canonical_name}")
            )


def _simplify_dataflow(pdg: Graph) -> None:
    pdg.set_dirty()

    while pdg.is_dirty:
        pdg.reset_dirty()

        _remove_unused_subgraphs(pdg)
        _propagate_constants(pdg)
        _inline_constants_into_expressions(pdg)
        _simplify_expressions(pdg)
        _replace_constant_expressions(pdg)


def _propagate_constants(pdg: Graph) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, (ScalarLiteral, CompositeLiteral)):
            continue
        _propagate_constant(pdg, node)


def _propagate_constant(pdg: Graph, lit: ScalarLiteral | CompositeLiteral) -> None:
    for _, target_node, edge in list(pdg.out_edges(lit, data="type")):
        if isinstance(edge, Keyword):
            assert isinstance(target_node, Task)
            continue
        if isinstance(edge, Composition):
            assert isinstance(target_node, CompositeLiteral)
            continue
        if isinstance(target_node, (Conditional, Loop)):
            continue
        if isinstance(edge, DefLoopItem):
            continue
        if isinstance(edge, Input):
            assert isinstance(target_node, Expression)
            # Handled in expression simplification
            continue

        is_var_def = isinstance(edge, Def) and isinstance(
            target_node, (Variable, IntermediateValue)
        )

        assert is_var_def, f"Impossible literal chain: {lit}-[{edge}]->{target_node}"

        # Replace (lit)-[DEF]->(var) with just (lit)
        # and thus also (lit)-[DEF]->(var)-[INPUT:_1]->(expr) to (lit)-[INPUT:_1]->(expr)
        _remove_edge(pdg, lit, target_node, edge)
        _replace_node(pdg, target_node, lit)


def _inline_constants_into_expressions(pdg: Graph) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, Expression):
            continue

        _inline_constants_into_expression(pdg, node)


def _is_simple_reference(ast: jnodes.Node) -> TypeGuard[jnodes.Name | jnodes.Template]:
    return isinstance(ast, jnodes.Name) or (
        isinstance(ast, jnodes.Template)
        and len(ast.body) == 1
        and isinstance(ast.body[0], jnodes.Output)
        and len(ast.body[0].nodes) == 1
        and isinstance(ast.body[0].nodes[0], jnodes.Name)
    )


def _is_simple_expression(ast: jnodes.Node) -> TypeGuard[jnodes.Template]:
    return (
        isinstance(ast, jnodes.Template)
        and len(ast.body) == 1
        and isinstance(ast.body[0], jnodes.Output)
    )


def _replace_simple_reference(
    pdg: Graph, node: Expression, inputs: dict[int, list[Node]]
) -> None:
    assert len(inputs) == 1 and 1 in inputs
    new_in_edges = [
        (src_node, edge)
        for src_node, _, edge in pdg.in_edges(node, "type")
        if not isinstance(edge, Input)
    ]
    new_out_edges = [
        (target_node, edge) for _, target_node, edge in pdg.out_edges(node, "type")
    ]

    for replacement in inputs[1]:
        for new_src, new_edge in new_in_edges:
            pdg.add_edge(new_src, replacement, new_edge)
        for new_target, new_edge in new_out_edges:
            pdg.add_edge(replacement, new_target, new_edge)

    pdg.remove_node(node)


def _inline_constants_into_expression(pdg: Graph, expr_node: Expression) -> None:
    inputs: dict[int, list[Node]] = defaultdict(list)
    for src_node, _, in_edge in pdg.in_edges(expr_node, "type"):
        if not isinstance(in_edge, Input):
            continue
        inputs[in_edge.param_idx].append(src_node)

    ast = _parse_ast(expr_node)
    if _is_simple_reference(ast):
        _replace_simple_reference(pdg, expr_node, inputs)
        return

    for param_idx, possible_values in inputs.items():
        # Cannot be inlined
        if not possible_values or not all(
            isinstance(value, ScalarLiteral) for value in possible_values
        ):
            continue

        new_in_edges = [
            (src_node, edge)
            for src_node, _, edge in pdg.in_edges(expr_node, "type")
            if not (isinstance(edge, Input) and edge.param_idx == param_idx)
        ]
        new_out_edges = [
            (target_node, edge)
            for _, target_node, edge in pdg.out_edges(expr_node, "type")
        ]

        for lit_node in possible_values:
            assert isinstance(lit_node, ScalarLiteral)

            new_node = Expression(
                _inline_constant_into_expression(
                    f"_{param_idx}", lit_node.value, expr_node
                ),
                expr_node.is_conditional,
                expr_node.orig_expr,
                expr_node.impure_components,
                location=expr_node.location,
            )
            pdg.add_node(new_node)
            for new_src, new_edge in new_in_edges:
                pdg.add_edge(new_src, new_node, new_edge)
            for new_src, _, new_edge in pdg.in_edges(lit_node, "type"):
                pdg.add_edge(new_src, new_node, new_edge)
            for new_target, new_edge in new_out_edges:
                pdg.add_edge(new_node, new_target, new_edge)

        pdg.remove_node(expr_node)
        # Further simplification in next fixpoint iteration possibly
        break


def _inline_constant_into_expression(
    name: str,
    value: Any,
    expr: Expression,
) -> str:
    ast = _parse_ast(expr)

    def check_node(node: jnodes.Node) -> bool:
        return (
            isinstance(node, jnodes.Name) and node.ctx == "load" and node.name == name
        )

    def replace_node(_: jnodes.Node) -> jnodes.Node:
        return jnodes.Const(value)

    new_ast = NodeReplacerVisitor(check_node, replace_node).visit(ast)
    new_expr = ASTStringifier().stringify(new_ast, expr.is_conditional)
    assert new_expr != expr.expr
    return new_expr


def _parse_ast(node: Expression) -> jnodes.Node:
    ast = (
        TemplateExpressionAST.parse(node.expr)
        if not node.is_conditional
        else TemplateExpressionAST.parse_conditional(node.expr, {})
    )
    return ensure_not_none(ast).ast_root


def _simplify_expressions(pdg: Graph) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, Expression):
            continue

        ast = _parse_ast(node)
        if _is_simple_expression(ast):
            assert isinstance(ast.body[0], jnodes.Output)
            _convert_top_level_const_to_templatedata(ast.body[0])
            _squash_templatedatas(ast.body[0])

        new_expr = ASTStringifier().stringify(ast, node.is_conditional)

        if new_expr != node.expr:
            new_node = Expression(
                new_expr,
                node.is_conditional,
                node.orig_expr,
                node.impure_components,
                location=node.location,
            )
            _replace_node(pdg, node, new_node)
            node = new_node

        _shift_input_indices(pdg, node)


def _shift_input_indices(pdg: Graph, expr_node: Expression) -> None:
    input_edges = [
        (src_node, in_edge)
        for src_node, _, in_edge in pdg.in_edges(expr_node, "type")
        if isinstance(in_edge, Input)
    ]

    new_idx = 1
    idx_mappings: dict[int, int] = {}
    for old_idx in sorted(set(edge.param_idx for _, edge in input_edges)):
        idx_mappings[old_idx] = new_idx
        new_idx += 1

    for src_node, edge in input_edges:
        new_idx = idx_mappings[edge.param_idx]
        if new_idx != edge.param_idx:
            _replace_edge(pdg, src_node, expr_node, edge, Input(new_idx))

    ast = _parse_ast(expr_node)

    class RenamerVisitor(NodeVisitor):
        def visit_Name(self, node: jnodes.Name) -> None:
            if node.ctx != "load":
                return

            try:
                var_idx = int(node.name.removeprefix("_"))
            except ValueError:
                return

            new_idx = idx_mappings[var_idx]
            node.name = f"_{new_idx}"

    RenamerVisitor().visit(ast)
    new_expr = ASTStringifier().stringify(ast, expr_node.is_conditional)
    if new_expr != expr_node.expr:
        new_node = Expression(
            new_expr,
            expr_node.is_conditional,
            expr_node.orig_expr,
            expr_node.impure_components,
            location=expr_node.location,
        )
        _replace_node(pdg, expr_node, new_node)


def _convert_top_level_const_to_templatedata(ast: jnodes.Output) -> None:
    for idx in range(len(ast.nodes)):
        child = ast.nodes[idx]
        if isinstance(child, jnodes.Const):
            ast.nodes[idx] = jnodes.TemplateData(str(child.value))


def _squash_templatedatas(ast: jnodes.Output) -> None:
    new_nodes: list[jnodes.Expr] = []
    for child in ast.nodes:
        if (
            not new_nodes
            or not isinstance(child, jnodes.TemplateData)
            or not isinstance(new_nodes[-1], jnodes.TemplateData)
        ):
            new_nodes.append(child)
        else:
            new_nodes[-1].data += child.data

    # HACK: Jinja2 strips trailing newlines, but we may have propagated some
    # E.g. "blabla{{ '\n' }}" which people use to force trailing newlines.
    # Restore those.
    if isinstance(new_nodes[-1], jnodes.TemplateData) and new_nodes[-1].data.endswith(
        "\n"
    ):
        new_nodes[-1].data = new_nodes[-1].data[:-1]
        if not new_nodes[-1].data:
            new_nodes = new_nodes[:-1]
        new_nodes.append(jnodes.Const("\n"))

    ast.nodes = new_nodes


def _replace_constant_expressions(pdg: Graph) -> None:
    for node in list(pdg.nodes()):
        if not isinstance(node, Expression):
            continue

        ast = _parse_ast(node)
        if isinstance(ast, jnodes.Const):
            lit_node = ScalarLiteral(extract_type_name(ast.value), ast.value)
        elif _is_simple_expression(ast):
            assert isinstance(ast.body[0], jnodes.Output)
            all_const = all(
                isinstance(child, jnodes.TemplateData) for child in ast.body[0].nodes
            )
            if not all_const:
                continue

            value = "".join(
                cast(jnodes.TemplateData, child).data for child in ast.body[0].nodes
            )
            lit_node = ScalarLiteral("str", value)
        else:
            continue

        _replace_node(pdg, node, lit_node)


def _normalize_data_types(pdg: Graph, module_kb: ModuleKnowledgeBase) -> None:
    tasks = [node for node in pdg.nodes() if isinstance(node, Task)]
    for task in tasks:
        module_info = module_kb.modules.get(task.action)
        if module_info is not None:
            _coerce_params(pdg, task, module_info)


def _coerce_params(pdg: Graph, task: Task, module_info: ModuleInfo) -> None:
    inputs = [(src_node, edge) for src_node, _, edge in pdg.in_edges(task, "type")]
    for input_node, input_edge in inputs:
        if not isinstance(input_edge, Keyword) or not isinstance(
            input_node, ScalarLiteral
        ):
            continue
        param_name = _keyword_to_option_name(input_edge.keyword)
        param_info = module_info.options.get(param_name)
        if not param_info:
            continue

        _coerce_param(pdg, input_node, task, input_edge, param_info)


def _coerce_param(
    pdg: Graph, lit: ScalarLiteral, task: Task, kw: Keyword, param_info: OptionInfo
) -> None:
    param_type = param_info.type
    if param_type is None:
        return
    if param_type == "path":
        # path coercer expands ~ and shell variables, we don't want that.
        param_type = "str"

    validator = DEFAULT_TYPE_VALIDATORS.get(param_type)  # pyright: ignore
    if validator is None:
        return

    try:
        validated_value = validator(lit.value)  # pyright: ignore
    except Exception as e:
        logger.warning(
            f"Parameter {kw.keyword} of value {lit.value!r} to task {task.action} may have a wrong type: {e}"
        )
        return

    if validated_value == lit.value:
        return
    logger.info(
        f"Coerced parameter {kw.keyword} of value {lit.value!r} to task {task.action} to type {param_type}: {validated_value!r}"
    )
    new_node = _create_literal_node(pdg, validated_value)

    for src_node, _, in_edge in pdg.in_edges(lit, "type"):
        pdg.add_edge(src_node, new_node, in_edge)
    pdg.add_edge(new_node, task, kw)
    _remove_edge(pdg, lit, task, kw)


def _create_literal_node(pdg: Graph, value: Any) -> ScalarLiteral | CompositeLiteral:
    if isinstance(value, (list, tuple, dict)):
        node = CompositeLiteral(extract_type_name(value))  # pyright: ignore
        pdg.add_node(node)
        children = (  # pyright: ignore
            value.items()
            if isinstance(value, dict)
            else enumerate(value)  # pyright: ignore
        )
        for child_key, child in children:  # pyright: ignore
            child_node = _create_literal_node(pdg, child)
            pdg.add_edge(
                child_node, node, Composition(str(child_key))  # pyright: ignore
            )
        return node

    lit = ScalarLiteral(extract_type_name(value), value)
    pdg.add_node(lit)
    return lit


def _remove_unused_subgraphs(pdg: Graph) -> None:
    old_num_nodes = len(pdg) + 1

    while len(pdg) != old_num_nodes:
        old_num_nodes = len(pdg)
        for node in list(pdg.nodes()):
            if isinstance(node, Task):
                continue
            if not pdg.out_edges(node):
                pdg.remove_node(node)


_NodeType = TypeVar("_NodeType", bound=Node)
_EdgeType = TypeVar("_EdgeType", bound=Edge)


def _replace_node(pdg: Graph, node: _NodeType, new_node: _NodeType) -> None:
    in_edges = pdg.in_edges(node, data="type")
    out_edges = pdg.out_edges(node, data="type")

    pdg.add_node(new_node)

    for source, _, in_edge in in_edges:
        pdg.add_edge(source, new_node, in_edge)
    for _, target, out_edge in out_edges:
        pdg.add_edge(new_node, target, out_edge)

    pdg.remove_node(node)


def _remove_edge(pdg: Graph, src_node: Node, target_node: Node, edge: Edge) -> None:
    edge_keys = ensure_not_none(pdg.get_edge_data(src_node, target_node))
    edge_key = ensure_not_none(
        first(
            edge_idx
            for edge_idx, edge_data in edge_keys.items()
            if edge_data["type"] == edge
        )
    )
    pdg.remove_edge(src_node, target_node, key=edge_key)


def _replace_edge(
    pdg: Graph,
    src_node: Node,
    target_node: Node,
    orig_edge: _EdgeType,
    new_edge: _EdgeType,
) -> None:
    _remove_edge(pdg, src_node, target_node, orig_edge)
    pdg.add_edge(src_node, target_node, new_edge)
