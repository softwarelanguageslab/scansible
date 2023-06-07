"""Extract information from template expressions."""
from __future__ import annotations

from typing import Any, cast

import os
import re
from collections.abc import Callable, Iterable

from attrs import frozen
from jinja2 import Environment, nodes
from jinja2.compiler import DependencyFinderVisitor
from jinja2.exceptions import TemplateSyntaxError
from jinja2.visitor import NodeVisitor
from loguru import logger

ANSIBLE_GLOBALS = frozenset({"lookup", "query", "q", "now", "finalize", "omit"})

OPERAND_TO_STR = {
    "eq": "==",
    "ne": "!=",
    "gt": ">",
    "lt": "<",
    "gteq": ">=",
    "lteq": "<=",
    "notin": "not in",
}


class ASTStringifier(NodeVisitor):
    def generic_visit(self, node: nodes.Node, *args: object, **kwargs: object) -> str:
        if isinstance(node, nodes.BinExpr):
            return self.visit_BinExpr(node)
        if isinstance(node, nodes.UnaryExpr):
            return self.visit_UnaryExpr(node)
        raise ValueError(f"Unsupported node: {node}")

    def stringify(self, node: nodes.Node, is_conditional: bool) -> str:
        generated = self.visit(node)
        self._check_correctness(node, generated, is_conditional)
        return generated  # type: ignore[no-any-return]

    def _check_correctness(
        self, node: nodes.Node, generated: str, is_conditional: bool
    ) -> None:
        reparsed = (
            Environment().parse(generated)
            if not is_conditional
            else parse_conditional(generated, Environment(), {})[0]
        )

        if reparsed == merge_consecutive_templatedata(node):
            return

        # Allow changing of bad conditionals which contain braces
        if is_conditional and isinstance(node, nodes.Template):
            return

        diffs = _find_ast_differences(reparsed, node)

        raise RuntimeError(
            f"""
                Bad stringification!
                {reparsed}
                vs
                {node}

                {self.visit(reparsed)}
                vs
                {generated}

                Diffs: {os.linesep.join(diffs)}

                Conditional: {is_conditional}
                """
        )

    def visit_Name(self, node: nodes.Name, **kwargs: Any) -> str:
        return node.name

    def visit_NSRef(self, node: nodes.NSRef, **kwargs: Any) -> str:
        return f"{node.name}.{node.attr}"

    def visit_Template(self, node: nodes.Template, **kwargs: Any) -> str:
        parts = [self.visit(child) for child in node.body]

        # Escape TemplateData ending with { followed by expression/statement,
        # otherwise subsequent parsing will fail. Similarly for TD starting with }
        # preceded by expression/statement.
        for idx, part in enumerate(parts):
            if (
                part.endswith("{")
                and len(parts) > (idx + 1)
                and parts[idx + 1].startswith(("{{ ", "{% "))
            ):
                # Turn "{{% if" into "{ {%- if" etc., which parses correctly.
                parts[idx + 1] = re.sub(r"(\{[\{%])", r" \1-", parts[idx + 1])
            if (
                part.startswith("}")
                and idx > 0
                and parts[idx - 1].endswith((" }}", " %}"))
            ):
                # Turn "endif %}}" into "endif -%} }" etc., which parses correctly.
                parts[idx - 1] = re.sub(r"([\}%]})", r"-\1 ", parts[idx - 1])

        rendered = "".join(parts)
        # Add additional trailing newline, Jinja2's parser consumes one.
        if rendered.endswith("\n"):
            rendered += "\n"
        return rendered

    def visit_Output(self, node: nodes.Output, **kwargs: Any) -> str:
        result = ""
        for child in node.nodes:
            if isinstance(child, nodes.TemplateData):
                result += self.visit(child)
            else:
                result += "{{ " + self.visit(child) + " }}"

        return result

    def visit_TemplateData(self, node: nodes.TemplateData, **kwargs: Any) -> str:
        if (
            "{{" in node.data
            or "}}" in node.data
            or "{%" in node.data
            or "%}" in node.data
        ):
            return "{% raw %}" + node.data + "{% endraw %}"
        return node.data

    def visit_Compare(self, node: nodes.Compare, **kwargs: Any) -> str:
        if len(node.ops) != 1:
            raise ValueError(f"Unsupported node: {node}")
        return f"({self.visit(node.expr)} {self.visit(node.ops[0])})"

    def visit_Operand(self, node: nodes.Operand, **kwargs: Any) -> str:
        return f"{OPERAND_TO_STR.get(node.op, node.op)} {self.visit(node.expr)}"

    def visit_Const(self, node: nodes.Const, **kwargs: Any) -> str:
        return repr(node.value)

    def visit_List(self, node: nodes.List, **kwargs: Any) -> str:
        return "[" + ", ".join(self.visit(item) for item in node.items) + "]"

    def visit_Dict(self, node: nodes.Dict, **kwargs: Any) -> str:
        return "{" + ", ".join(self.visit(item) for item in node.items) + "}"

    def visit_Pair(self, node: nodes.Pair, **kwargs: Any) -> str:
        return f"{self.visit(node.key)}: {self.visit(node.value)}"

    def visit_Not(self, node: nodes.Not, **kwargs: Any) -> str:
        if isinstance(node.node, nodes.Test):
            return self.visit_Test(node.node, negate=True)
        return f"(not {self.visit(node.node)})"

    def visit_BinExpr(self, node: nodes.BinExpr, **kwargs: Any) -> str:
        return f"({self.visit(node.left)} {node.operator} {self.visit(node.right)})"

    def visit_UnaryExpr(self, node: nodes.UnaryExpr, **kwargs: Any) -> str:
        return f"{node.operator} {self.visit(node.node)}"

    def visit_Concat(self, node: nodes.Concat, **kwargs: Any) -> str:
        return "(" + " ~ ".join(self.visit(child) for child in node.nodes) + ")"

    def visit_CondExpr(self, node: nodes.CondExpr, **kwargs: Any) -> str:
        base = f"({self.visit(node.expr1)} if {self.visit(node.test)}"
        if node.expr2 is None:
            return base + ")"
        else:
            return f"{base} else {self.visit(node.expr2)})"

    def visit_If(self, node: nodes.If, **kwargs: Any) -> str:
        head = (
            "{% if "
            + self.visit(node.test)
            + " %}"
            + "".join(self.visit(child) for child in node.body)
        )

        elifs: list[str] = []
        for elif_ in node.elif_:
            assert not elif_.else_ and not elif_.elif_
            elifs.append(
                "{% elif "
                + self.visit(elif_.test)
                + " %}"
                + "".join(self.visit(child) for child in elif_.body)
            )

        if node.else_:
            tail = (
                "{% else %}"
                + "".join(self.visit(child) for child in node.else_)
                + "{% endif %}"
            )
        else:
            tail = "{% endif %}"

        return f"{head}{''.join(elifs)}{tail}"

    def visit_FilterBlock(self, node: nodes.FilterBlock, **kwargs: Any) -> str:
        head = "{% filter " + self.visit(node.filter) + " %}"
        return (
            head + "".join(self.visit(child) for child in node.body) + "{% endfilter %}"
        )

    def visit_For(self, node: nodes.For, **kwargs: Any) -> str:
        if node.recursive:
            raise ValueError(f"Unsupported node: {node}")

        head = "{% for " + self.visit(node.target) + " in " + self.visit(node.iter)
        if node.test:
            head += " if " + self.visit(node.test)
        head += " %}"
        body = "".join(self.visit(child) for child in node.body)
        if node.else_:
            else_ = "{% else %}" + "".join(self.visit(child) for child in node.else_)
        else:
            else_ = ""
        end = "{% endfor %}"

        return f"{head}{body}{else_}{end}"

    def visit_Tuple(self, node: nodes.Tuple, **kwargs: Any) -> str:
        return f'({", ".join(self.visit(child) for child in node.items)})'

    def visit_Assign(self, node: nodes.Assign, **kwargs: Any) -> str:
        assign = f"set {self.visit(node.target)} = {self.visit(node.node)}"
        return "{% " + assign + " %}"

    def visit_AssignBlock(self, node: nodes.AssignBlock, **kwargs: Any) -> str:
        if node.filter is not None:
            raise ValueError(f"Unsupported node: {node}")
        head = "{% set " + self.visit(node.target) + "%}"
        body = "".join(self.visit(child) for child in node.body)
        tail = "{% endset %}"
        return "".join((head, body, tail))

    def visit_Test(self, node: nodes.Test, negate: bool = False, **kwargs: Any) -> str:
        lhs = self.visit(node.node)
        rhs = self._stringify_call(
            node.name, node.args, node.kwargs, node.dyn_args, node.dyn_kwargs
        )
        if negate:
            return f"{lhs} is not {rhs}"
        else:
            return f"{lhs} is {rhs}"

    def visit_Filter(self, node: nodes.Filter, **kwargs: Any) -> str:
        filter_call = self._stringify_call(
            node.name, node.args, node.kwargs, node.dyn_args, node.dyn_kwargs
        )
        if node.node is not None:
            rendered = f"{self.visit(node.node)} | {filter_call}"
        else:
            rendered = filter_call
        if kwargs.get("parenthesize"):
            return f"({rendered})"
        return rendered

    def visit_Call(self, node: nodes.Call, **kwargs: Any) -> str:
        return self._stringify_call(
            self.visit(node.node),
            node.args,
            node.kwargs,
            node.dyn_args,
            node.dyn_kwargs,
            force_parens=True,
        )

    def visit_Getitem(self, node: nodes.Getitem, **kwargs: Any) -> str:
        return f"{self.visit(node.node, parenthesize=True)}[{self.visit(node.arg)}]"

    def visit_Getattr(self, node: nodes.Getattr, **kwargs: Any) -> str:
        return f"{self.visit(node.node, parenthesize=True)}.{node.attr}"

    def visit_Keyword(self, node: nodes.Keyword, **kwargs: Any) -> str:
        return f"{node.key}={self.visit(node.value)}"

    def visit_Slice(self, node: nodes.Slice, **kwargs: Any) -> str:
        start = self.visit(node.start) if node.start else ""
        stop = self.visit(node.stop) if node.stop else ""
        if node.step:
            return f"{start}:{stop}:{self.visit(node.step)}"
        else:
            return f"{start}:{stop}"

    def _stringify_call(
        self,
        name: str,
        args: list[nodes.Expr],
        kwargs: list[nodes.Pair] | list[nodes.Keyword],
        dyn_args: nodes.Expr | None,
        dyn_kwargs: nodes.Expr | None,
        *,
        force_parens: bool = False,
    ) -> str:
        if (
            not args
            and not kwargs
            and not dyn_args
            and not dyn_kwargs
            and not force_parens
        ):
            return name

        args_list = ", ".join(self.visit(arg) for arg in args)
        kwargs_list = ", ".join(self.visit(kwarg) for kwarg in kwargs)
        dyn_args_str = f"*{self.visit(dyn_args)}" if dyn_args is not None else ""
        dyn_kwargs_str = f"**{self.visit(dyn_kwargs)}" if dyn_kwargs is not None else ""
        args_str = ", ".join(
            part
            for part in (args_list, kwargs_list, dyn_args_str, dyn_kwargs_str)
            if part
        )
        return f"{name}({args_str})"


class NodeReplacerVisitor(NodeVisitor):
    def __init__(
        self,
        matcher: Callable[[nodes.Node], bool],
        replacer: Callable[[nodes.Node], Any],
    ) -> None:
        self.match = matcher
        self.replace = replacer

    def generic_visit(self, node: nodes.Node, *args: object, **kwargs: object) -> None:
        if isinstance(node, nodes.BinExpr):
            self.visit_BinExpr(node)
            return
        if isinstance(node, nodes.UnaryExpr):
            self.visit_UnaryExpr(node)
            return

        if list(node.iter_child_nodes()):
            raise ValueError(f"Unsupported node: {node}")

    def visit(self, node: nodes.Node, *args: object, **kwargs: object) -> nodes.Node:
        if self.match(node):
            return self.replace(node)  # type: ignore[no-any-return]
        super().visit(node)
        return node

    def _match_and_replace(self, node: nodes.Node) -> Any:
        if self.match(node):
            return self.replace(node)
        else:
            self.visit(node)
            return node

    def _match_and_replace_list(self, nodes: list[nodes.Node] | None) -> None:
        if nodes is None:
            return
        for idx in range(len(nodes)):
            nodes[idx] = self._match_and_replace(nodes[idx])

    def visit_Template(self, node: nodes.Template) -> None:
        self._match_and_replace_list(node.body)

    def visit_Output(self, node: nodes.Output) -> None:
        self._match_and_replace_list(cast(list[nodes.Node], node.nodes))

    def visit_Compare(self, node: nodes.Compare) -> None:
        node.expr = self._match_and_replace(node.expr)
        self._match_and_replace_list(cast(list[nodes.Node], node.ops))

    def visit_Operand(self, node: nodes.Operand) -> None:
        node.expr = self._match_and_replace(node.expr)

    def visit_List(self, node: nodes.List) -> None:
        self._match_and_replace_list(cast(list[nodes.Node], node.items))

    def visit_Dict(self, node: nodes.Dict) -> None:
        self._match_and_replace_list(cast(list[nodes.Node], node.items))

    def visit_Pair(self, node: nodes.Pair) -> None:
        node.key = self._match_and_replace(node.key)
        node.value = self._match_and_replace(node.value)

    def visit_Not(self, node: nodes.Not) -> None:
        node.node = self._match_and_replace(node.node)

    def visit_BinExpr(self, node: nodes.BinExpr) -> None:
        node.left = self._match_and_replace(node.left)
        node.right = self._match_and_replace(node.right)

    def visit_UnaryExpr(self, node: nodes.UnaryExpr) -> None:
        node.node = self._match_and_replace(node.node)

    def visit_Concat(self, node: nodes.Concat) -> None:
        self._match_and_replace_list(cast(list[nodes.Node], node.nodes))

    def visit_CondExpr(self, node: nodes.CondExpr) -> None:
        node.expr1 = self._match_and_replace(node.expr1)
        node.test = self._match_and_replace(node.test)
        if node.expr2 is not None:
            node.expr2 = self._match_and_replace(node.expr2)

    def visit_If(self, node: nodes.If) -> None:
        node.test = self._match_and_replace(node.test)
        self._match_and_replace_list(node.body)
        self._match_and_replace_list(cast(list[nodes.Node], node.elif_))
        self._match_and_replace_list(node.else_)

    def visit_FilterBlock(self, node: nodes.FilterBlock) -> None:
        node.filter = self._match_and_replace(node.filter)
        self._match_and_replace_list(node.body)

    def visit_For(self, node: nodes.For) -> None:
        node.target = self._match_and_replace(node.target)
        node.iter = self._match_and_replace(node.iter)
        self._match_and_replace_list(node.body)
        self._match_and_replace_list(node.else_)

    def visit_Tuple(self, node: nodes.Tuple) -> None:
        self._match_and_replace_list(cast(list[nodes.Node], node.items))

    def visit_Assign(self, node: nodes.Assign) -> None:
        node.node = self._match_and_replace(node.node)
        node.target = self._match_and_replace(node.target)

    def visit_AssignBlock(self, node: nodes.AssignBlock) -> None:
        self._match_and_replace_list(node.body)
        node.target = self._match_and_replace(node.target)
        if node.filter is not None:
            node.filter = self._match_and_replace(node.filter)

    def visit_Slice(self, node: nodes.Slice) -> None:
        if node.start:
            node.start = self._match_and_replace(node.start)
        if node.stop:
            node.stop = self._match_and_replace(node.stop)
        if node.step:
            node.step = self._match_and_replace(node.step)

    def visit_Test(self, node: nodes.Test) -> None:
        node.node = self._match_and_replace(node.node)
        self._match_and_replace_list(cast(list[nodes.Node], node.args))
        self._match_and_replace_list(cast(list[nodes.Node], node.kwargs))
        if node.dyn_args is not None:
            node.dyn_args = self._match_and_replace(node.dyn_args)
        if node.dyn_kwargs is not None:
            node.dyn_kwargs = self._match_and_replace(node.dyn_kwargs)

    def visit_Filter(self, node: nodes.Filter) -> None:
        if node.node is not None:
            node.node = self._match_and_replace(node.node)
        self._match_and_replace_list(cast(list[nodes.Node], node.args))
        self._match_and_replace_list(cast(list[nodes.Node], node.kwargs))
        if node.dyn_args is not None:
            node.dyn_args = self._match_and_replace(node.dyn_args)
        if node.dyn_kwargs is not None:
            node.dyn_kwargs = self._match_and_replace(node.dyn_kwargs)

    def visit_Call(self, node: nodes.Call) -> None:
        node.node = self._match_and_replace(node.node)
        self._match_and_replace_list(cast(list[nodes.Node], node.args))
        self._match_and_replace_list(cast(list[nodes.Node], node.kwargs))
        if node.dyn_args is not None:
            node.dyn_args = self._match_and_replace(node.dyn_args)
        if node.dyn_kwargs is not None:
            node.dyn_kwargs = self._match_and_replace(node.dyn_kwargs)

    def visit_Getitem(self, node: nodes.Getitem) -> None:
        node.node = self._match_and_replace(node.node)
        node.arg = self._match_and_replace(node.arg)

    def visit_Getattr(self, node: nodes.Getattr) -> None:
        node.node = self._match_and_replace(node.node)

    def visit_Keyword(self, node: nodes.Keyword) -> None:
        node.value = self._match_and_replace(node.value)


def _fix_escaped_templatedata(children: list[nodes.Expr]) -> list[nodes.Expr]:
    # Re-escape double braces which may have been propagated from constants.
    # E.g. "blabla {{ '{{' }}" which otherwise would get interpreted as a Jinja
    # template.
    # Alternatively we could ignore these in the Const -> TemplateData conversion,
    # but we'd like to also canonicalize "blabla {{ '{{ abc'}}" to "blabla {{ "{{" }} abc"\
    new_nodes: list[nodes.Expr] = []
    for node in children:
        if not isinstance(node, nodes.TemplateData) or (
            "{{" not in node.data and "}}" not in node.data
        ):
            new_nodes.append(node)
            continue

        new_data = re.sub(r"([\{\}]{3,}|[%\{]{2,}|[%\}]{2,})", r'{{ "\1" }}', node.data)
        new_body = Environment().parse(new_data).body
        assert len(new_body) == 1 and isinstance(new_body[0], nodes.Output)
        new_nodes.extend(new_body[0].nodes)

    return new_nodes


def merge_consecutive_templatedata(ast: nodes.Node) -> nodes.Node:
    def _check_node(node: nodes.Node) -> bool:
        return isinstance(node, nodes.Output)

    def _replace_node(node: nodes.Node) -> nodes.Node:
        assert isinstance(node, nodes.Output)
        new_nodes: list[nodes.Expr] = []
        for child in node.nodes:
            if (
                not new_nodes
                or not isinstance(child, nodes.TemplateData)
                or not isinstance(new_nodes[-1], nodes.TemplateData)
            ):
                new_nodes.append(child)
            else:
                new_nodes[-1].data += child.data

        new_nodes = _fix_escaped_templatedata(new_nodes)

        # Remove any empty template data. This doesn't functionally change anything
        # in the expression, but it leads to a difference in the stringifier.
        if len(new_nodes) > 1:
            new_nodes = [
                node
                for node in new_nodes
                if not (isinstance(node, nodes.TemplateData) and not node.data)
            ]

        return nodes.Output(new_nodes)

    return NodeReplacerVisitor(_check_node, _replace_node).visit(ast)


def _find_ast_differences(a: nodes.Node, b: nodes.Node) -> Iterable[str]:
    if a == b:
        return

    if type(a) != type(b):
        yield f"{type(a)} vs {type(b)}"
        return

    a_children = list(a.iter_child_nodes())
    b_children = list(b.iter_child_nodes())

    if a_children == b_children:
        yield f"{type(a)}: Attributes differ: {list(a.iter_fields())} vs {list(b.iter_fields())}"
        return

    if len(a_children) != len(b_children):
        yield f"{type(a)}: {len(a_children)} vs {len(b_children)} children: {a} vs {b}"
        return

    for a_child, b_child in zip(a_children, b_children):
        yield from _find_ast_differences(a_child, b_child)


def generify_var_references(ast: nodes.Node) -> tuple[nodes.Node, dict[str, int]]:
    param_indices: dict[str, int] = {}
    next_idx = 1

    class Visitor(NodeVisitor):
        def __init__(self) -> None:
            self.declared: set[str] = set()

        def visit_Name(self, node: nodes.Name) -> None:
            if node.ctx == "store":
                self.declared.add(node.name)
                return

            assert node.ctx == "load"

            if node.name in ANSIBLE_GLOBALS or node.name in self.declared:
                return

            if node.name not in param_indices:
                nonlocal next_idx
                param_indices[node.name] = next_idx
                next_idx += 1

            node.name = f"_{param_indices[node.name]}"

    Visitor().visit(ast)
    return ast, param_indices


class LookupTarget:
    pass


@frozen(hash=True)
class NamedLookupTarget(LookupTarget):
    name: str


class LookupTargetLiteral(NamedLookupTarget):
    def __str__(self) -> str:
        return f"'{self.name}'"


class LookupTargetVariable(NamedLookupTarget):
    def __str__(self) -> str:
        return self.name


@frozen(hash=True)
class LookupTargetUnknown(LookupTarget):
    value: str

    def __str__(self) -> str:
        return self.value


def parse_wrapped_conditional(expr: str, env: Environment) -> nodes.Node:
    expr = "{% if " + expr + " %} True {% else %} False {% endif %}"
    ast = env.parse(expr)
    assert isinstance(ast.body[0], nodes.If)
    return ast.body[0].test


def parse_conditional(
    expr: str, env: Environment, var_mappings: dict[str, str]
) -> tuple[nodes.Node, set[str]]:
    ast = env.parse(expr)
    if not ast.body:
        return ast, set()

    assert len(ast.body) == 1

    if not isinstance(ast.body[0], nodes.Output):
        # Definitely an expression, and likely one we cannot handle properly.
        logger.warning(
            f"Weird conditional ({ast.body[0].__class__.__name__}) found: {expr!r}"
        )
        return ast, set()

    if all(isinstance(child, nodes.TemplateData) for child in ast.body[0].nodes):
        # The condition is not a template expression. Wrap it as a condition
        return parse_wrapped_conditional(expr, env), set()

    # This conditional template expression contains braces.
    # Ansible will template this, then afterwards feed the result
    # back into the templar recursively. We can't do that, because
    # we may not have enough information to evaluate the template.
    # Instead, we go with a best effort approach.

    # If there is exactly one part to the template, and it references
    # a variable of which we know the value, we substitute it. We also indicate
    # the additional reference to the first variable
    if (
        len(ast.body[0].nodes) == 1
        and isinstance(ast.body[0].nodes[0], nodes.Name)
        and ast.body[0].nodes[0].name in var_mappings
    ):
        var_name = ast.body[0].nodes[0].name
        var_str = var_mappings[var_name]
        return parse_wrapped_conditional(var_str, env), {var_name}

    # Otherwise, we don't know anything about the variable, so we parse it as
    # is.
    return ast, set()


def create_lookup_target(node: nodes.Node) -> LookupTarget:
    if isinstance(node, nodes.Name):
        return LookupTargetVariable(name=node.name)

    if not isinstance(node, nodes.Const) or not isinstance(node.value, str):
        logger.warning(
            f"Not extracting lookup plugin target, not a string or variable: {node}"
        )
        return LookupTargetUnknown(value=str(node))

    return LookupTargetLiteral(name=node.value)


class FindUndeclaredVariablesVisitor(NodeVisitor):
    def __init__(self, declared: frozenset[str]) -> None:
        self.declared: set[str] = set(declared)
        self.undeclared: set[str] = set()

    def visit_Name(self, name_node: nodes.Name) -> None:
        if name_node.ctx == "load" and name_node.name not in self.declared:
            self.undeclared.add(name_node.name)
        else:
            self.declared.add(name_node.name)

    def visit_Block(self, _block_node: nodes.Block) -> None:
        # Don't visit blocks, they may have local declarations.
        # Not sure if we'd ever need to visit blocks.
        pass


class TemplateExpressionAST:
    def __init__(
        self,
        ast_root: nodes.Node,
        raw: str,
        extra_references: set[str] | None = None,
        is_conditional: bool = False,
    ) -> None:
        self.ast_root = ast_root
        self.raw = raw
        self.is_conditional = is_conditional

        var_visitor = FindUndeclaredVariablesVisitor(ANSIBLE_GLOBALS)
        var_visitor.visit(ast_root)
        self.referenced_variables = var_visitor.undeclared
        if extra_references is not None:
            self.referenced_variables |= extra_references

        dep_visitor = DependencyFinderVisitor()
        dep_visitor.visit(ast_root)

        self.used_tests = dep_visitor.tests
        self.used_filters = dep_visitor.filters

        self.uses_now = any(
            call_node.node.name == "now"
            for call_node in ast_root.find_all(nodes.Call)
            if isinstance(call_node.node, nodes.Name)
        )
        self.used_lookups: set[LookupTarget] = {
            create_lookup_target(call_node.args[0])
            for call_node in ast_root.find_all(nodes.Call)
            if (
                (isinstance(call_node.node, nodes.Name))
                and call_node.node.name in ("lookup", "query", "q")
            )
        }

    def is_literal(self) -> bool:
        return not self.raw or (
            isinstance(self.ast_root, nodes.Template)
            and len(self.ast_root.body) == 1
            and isinstance(self.ast_root.body[0], nodes.Output)
            and len(self.ast_root.body[0].nodes) == 1
            and isinstance(self.ast_root.body[0].nodes[0], nodes.TemplateData)
        )

    @classmethod
    def parse(cls, expression: str) -> TemplateExpressionAST | None:
        """
        Parse a bare template expression to an AST.
        For conditionals, use `parse_conditional`.

        :param      expression:      The template expression
        :type       expression:      str

        :returns:   The template expression AST instance.
        :rtype:     TemplateExpressionAST
        """
        env = Environment(cache_size=0)

        try:
            return cls(env.parse(expression), expression)
        except TemplateSyntaxError as tse:
            logger.error("Template syntax error: " + str(tse))
            return None

    @classmethod
    def parse_conditional(
        cls, expression: str, variable_mappings: dict[str, str]
    ) -> TemplateExpressionAST | None:
        """
        Parse a template expression to an AST.

        :param      expression:         The template expression
        :type       expression:         str
        :param      variable_mappings:  Mappings from variables to their
                                        initialisers, used to resolve
                                        multi-level expressions.
        :type       variable_mappings:  dict[str, str]

        :returns:   The template expression AST instance.
        :rtype:     TemplateExpressionAST
        """
        env = Environment(cache_size=0)

        try:
            ast, extra_references = parse_conditional(
                expression, env, variable_mappings
            )
            return cls(ast, expression, extra_references, True)
        except TemplateSyntaxError as tse:
            logger.error("Template syntax error: " + str(tse))
            return None
