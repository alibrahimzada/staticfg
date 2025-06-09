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

    def build(self, name: str, statements: List[str], params: List[str] = None) -> DFG:
        self.nodes = []
        self.current_cond = None
        # Add parameter nodes similar to the Python DFG builder
        if params:
            for param in params:
                self.add_node(param)
        for stmt in statements:
            stmt = stmt.strip()
            if stmt.startswith('if') and '(' in stmt:
                cond = stmt[stmt.find('(') + 1: stmt.rfind(')')]
                vars_ = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cond)))
                self.add_node(cond, vars_)
                self.current_cond = cond
            elif stmt.startswith('else'):
                if self.current_cond:
                    neg = f'not ({self.current_cond})'
                    vars_ = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', self.current_cond)))
                    self.add_node(neg, vars_)
                    self.current_cond = neg
                else:
                    self.current_cond = None
            elif stmt.startswith('return'):
                expr = stmt[len('return'):].strip()
                if expr.endswith(';'):
                    expr = expr[:-1].strip()
                vars_ = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr)))
                deps = [self.current_cond] if self.current_cond else vars_
                self.add_node(expr or 'return', deps)
            else:
                self.add_node(stmt)
        return DFG(name, self.nodes)

    def build_from_src(self, name: str, src: str) -> DFG:
        start_body = src.find('{')
        header = src[:start_body]
        end = src.rfind('}')
        body = src[start_body + 1:end]
        pattern = r'(?:if\s*\([^\)]+\)\s*\{?|else\s*\{?|case[^:]*:|default:|[^;{}]+;)'
        stmts = [part.strip() for part in re.findall(pattern, body)]

        # Extract parameter names from the method header
        params = []
        if '(' in header and ')' in header:
            param_list = header[header.find('(') + 1: header.rfind(')')]
            for p in param_list.split(','):
                p = p.strip()
                if not p:
                    continue
                m = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\])*$', p)
                if m:
                    params.append(m.group(1))

        return self.build(name, stmts, params)

    def build_from_file(self, name: str, filepath: str) -> DFG:
        with open(filepath, 'r') as src_file:
            src = src_file.read()
        return self.build_from_src(name, src)
