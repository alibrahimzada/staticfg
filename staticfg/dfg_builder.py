"""Basic Python data flow graph builder.

This version follows a more structured approach inspired by the
``CFGBuilder`` implementation.  A Python function is first parsed into an
AST, a symbol table is created using :mod:`symtable` and then a simple
data flow analysis is performed while visiting the AST.  The resulting
``DFG`` can be visualised using :mod:`graphviz` just like the control
flow graphs.
"""

import ast
import symtable
from dataclasses import dataclass, field
from typing import List, Optional

import graphviz as gv
from .builder import CFGBuilder

@dataclass
class DFGNode:
    name: str
    depends_on: List[str] = field(default_factory=list)

class DFG:
    """Simple data structure to hold DFG nodes and export a graphviz view."""

    def __init__(self, name: str, nodes: List[DFGNode]):
        self.name = name
        self.nodes = nodes

    def _build_visual(self, format: str = "pdf", calls: bool = True):
        graph = gv.Digraph(name=f"cluster{self.name}", format=format)
        for node in self.nodes:
            graph.node(node.name, label=node.name)
        for node in self.nodes:
            for dep in node.depends_on:
                graph.edge(dep, node.name)
        return graph

    def build_visual(self, filepath: str, format: str = "pdf", calls: bool = True, show: bool = True):
        graph = self._build_visual(format, calls)
        graph.render(filepath, view=show)


class DFGBuilder(ast.NodeVisitor):
    """Build a simple data flow graph for a Python function."""

    def __init__(self):
        # Collected :class:`DFGNode` objects.
        self.nodes: List[DFGNode] = []
        # Track the condition currently in scope (e.g. from if/loop statements).
        self.current_cond: Optional[str] = None
        self.symtable = None
        self.cfg = None

    def add_node(self, name: str, deps=None):
        self.nodes.append(DFGNode(name, deps or []))

    def get_vars(self, node):
        # Collect variable names referenced in ``node`` without duplicates
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
        return list(dict.fromkeys(names))

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------
    def parse(self, src: str) -> ast.AST:
        """Parse ``src`` and return its AST."""
        return ast.parse(src)

    def build_symbol_table(self, src: str) -> None:
        """Create a symbol table for ``src`` using :mod:`symtable`."""
        try:
            self.symtable = symtable.symtable(src, "dfg", "exec")
        except SyntaxError:
            self.symtable = None

    def build_cfg(self, name: str, tree: ast.AST) -> None:
        """Build a CFG from ``tree`` to help with ordering of statements."""
        self.cfg = CFGBuilder().build(name, tree)

    def build(self, name: str, tree: ast.AST, src: str = "") -> DFG:
        """Build a :class:`DFG` from ``tree``."""
        self.nodes = []
        self.current_cond = None
        if src:
            self.build_symbol_table(src)
        self.build_cfg(name, tree)
        self.visit(tree)
        return DFG(name, self.nodes)

    def build_from_src(self, name: str, src: str) -> DFG:
        """Build a :class:`DFG` from a source string."""
        tree = self.parse(src)
        return self.build(name, tree, src)

    def build_from_file(self, name: str, filepath: str) -> DFG:
        with open(filepath, "r") as src_file:
            src = src_file.read()
        return self.build_from_src(name, src)

    # Visitors
    def visit_FunctionDef(self, node):
        for arg in node.args.args:
            self.add_node(arg.arg)
        for stmt in node.body:
            self.visit(stmt)

    def visit_If(self, node):
        cond = ast.unparse(node.test).strip()
        self.add_node(cond, self.get_vars(node.test))
        prev_cond = self.current_cond
        self.current_cond = cond
        for s in node.body:
            self.visit(s)
        if node.orelse:
            neg = f"not ({cond})"
            self.add_node(neg, self.get_vars(node.test))
            self.current_cond = neg
            for s in node.orelse:
                self.visit(s)
        self.current_cond = prev_cond

    def visit_Return(self, node):
        expr = ast.unparse(node.value).strip()
        deps = [self.current_cond] if self.current_cond else self.get_vars(node.value)
        self.add_node(expr, deps)

    def visit_Expr(self, node):
        expr = ast.unparse(node.value).strip()
        deps = self.get_vars(node.value)
        if self.current_cond:
            deps.append(self.current_cond)
        self.add_node(expr, deps)

    def visit_Assign(self, node):
        deps = self.get_vars(node.value)
        if self.current_cond:
            deps.append(self.current_cond)
        for target in node.targets:
            name = ast.unparse(target).strip()
            self.add_node(name, deps)
        self.generic_visit(node.value)

    def visit_AugAssign(self, node):
        deps = self.get_vars(node.value) + self.get_vars(node.target)
        if self.current_cond:
            deps.append(self.current_cond)
        name = ast.unparse(node.target).strip()
        self.add_node(name, deps)
        self.generic_visit(node.value)

    visit_AnnAssign = visit_Assign

    def visit_While(self, node):
        cond = ast.unparse(node.test).strip()
        self.add_node(cond, self.get_vars(node.test))
        prev_cond = self.current_cond
        self.current_cond = cond
        for s in node.body:
            self.visit(s)
        if node.orelse:
            neg = f"not ({cond})"
            self.add_node(neg, self.get_vars(node.test))
            self.current_cond = neg
            for s in node.orelse:
                self.visit(s)
        self.current_cond = prev_cond

    def visit_For(self, node):
        iter_expr = ast.unparse(node.iter).strip()
        target_text = ast.unparse(node.target).strip()
        cond = f"for {target_text} in {iter_expr}"
        self.add_node(cond, self.get_vars(node.iter))
        prev_cond = self.current_cond
        self.current_cond = cond
        # assignment of iteration variable
        deps = self.get_vars(node.iter)
        if self.current_cond:
            deps.append(self.current_cond)
        self.add_node(target_text, deps)
        for s in node.body:
            self.visit(s)
        if node.orelse:
            neg = f"not ({cond})"
            self.add_node(neg, self.get_vars(node.iter))
            self.current_cond = neg
            for s in node.orelse:
                self.visit(s)
        self.current_cond = prev_cond


    def generic_visit(self, node):
        super().generic_visit(node)
