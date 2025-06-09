"""Basic Python data flow graph builder."""

import ast
from dataclasses import dataclass, field
from typing import List
import graphviz as gv

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
    def __init__(self):
        self.nodes: List[DFGNode] = []
        self.current_cond = None

    def add_node(self, name: str, deps=None):
        self.nodes.append(DFGNode(name, deps or []))

    def get_vars(self, node):
        return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]

    def build(self, name: str, tree: ast.AST) -> DFG:
        self.nodes = []
        self.current_cond = None
        self.visit(tree)
        return DFG(name, self.nodes)

    def build_from_src(self, name: str, src: str) -> DFG:
        tree = ast.parse(src)
        return self.build(name, tree)

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
            self.current_cond = f"not ({cond})"
            for s in node.orelse:
                self.visit(s)
        self.current_cond = prev_cond

    def visit_Return(self, node):
        expr = ast.unparse(node.value).strip()
        deps = [self.current_cond] if self.current_cond else self.get_vars(node.value)
        self.add_node(expr, deps)

    def generic_visit(self, node):
        super().generic_visit(node)
