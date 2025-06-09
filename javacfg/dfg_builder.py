"""Basic Java data flow graph builder used for tests."""

import re
from dataclasses import dataclass, field
from typing import List
import graphviz as gv


@dataclass
class DFGNode:
    name: str
    depends_on: List[str] = field(default_factory=list)


class DFG:
    """Container for Java data flow graph nodes."""

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


class DFGBuilder:
    def __init__(self):
        self.nodes: List[DFGNode] = []
        self.current_cond = None

    def add_node(self, name: str, deps=None):
        self.nodes.append(DFGNode(name, deps or []))

    def build(self, name: str, statements: List[str]) -> DFG:
        self.nodes = []
        self.current_cond = None
        for stmt in statements:
            stmt = stmt.strip()
            if stmt.startswith('if') and '(' in stmt:
                cond = stmt[stmt.find('(')+1:stmt.rfind(')')]
                vars_ = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cond)
                self.add_node(cond, vars_)
                self.current_cond = cond
            elif stmt.startswith('else'):
                if self.current_cond:
                    neg = f'not ({self.current_cond})'
                    vars_ = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', self.current_cond)
                    self.add_node(neg, vars_)
                    self.current_cond = neg
                else:
                    self.current_cond = None
            elif stmt.startswith('return'):
                self.add_node(stmt, [self.current_cond] if self.current_cond else [])
            else:
                self.add_node(stmt)
        return DFG(name, self.nodes)

    def build_from_src(self, name: str, src: str) -> DFG:
        start = src.find('{') + 1
        end = src.rfind('}')
        body = src[start:end]
        pattern = r'(?:if\s*\([^\)]+\)\s*\{?|else\s*\{?|case[^:]*:|default:|[^;{}]+;)'
        stmts = [part.strip() for part in re.findall(pattern, body)]
        return self.build(name, stmts)

    def build_from_file(self, name: str, filepath: str) -> DFG:
        with open(filepath, 'r') as src_file:
            src = src_file.read()
        return self.build_from_src(name, src)
