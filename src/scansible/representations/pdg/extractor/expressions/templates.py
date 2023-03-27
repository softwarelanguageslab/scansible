"""Extract information from template expressions."""
from __future__ import annotations

from attrs import frozen
from jinja2 import Environment, nodes
from jinja2.compiler import DependencyFinderVisitor
from jinja2.exceptions import TemplateSyntaxError
from jinja2.visitor import NodeVisitor
from loguru import logger

ANSIBLE_GLOBALS = frozenset({"lookup", "query", "q", "now", "finalize", "omit"})


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

    if len(ast.body[0].nodes) == 1 and isinstance(
        ast.body[0].nodes[0], nodes.TemplateData
    ):
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
        self, ast_root: nodes.Node, raw: str, extra_references: set[str] | None = None
    ) -> None:
        self.ast_root = ast_root
        self.raw = raw

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
            return cls(ast, expression, extra_references)
        except TemplateSyntaxError as tse:
            logger.error("Template syntax error: " + str(tse))
            return None
