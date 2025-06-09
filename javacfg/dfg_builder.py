"""Basic Java data flow graph builder."""

import re
from dataclasses import dataclass, field
from typing import List
import graphviz as gv

try:
    from tree_sitter_languages import get_parser
except Exception:  # pragma: no cover - optional dependency
    get_parser = None


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
        # Use the same parser as the CFG builder if available
        if get_parser is not None:
            try:
                self.parser = get_parser("java")
            except Exception:  # pragma: no cover - handled in tests
                self.parser = None
        else:  # pragma: no cover - optional dependency missing
            self.parser = None

    def add_node(self, name: str, deps=None):
        self.nodes.append(DFGNode(name, deps or []))

    def get_vars(self, text: str) -> List[str]:
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
        return list(dict.fromkeys(names))

    def get_text(self, node):
        return node.text.decode()

    # ----- tree-sitter traversal helpers -----
    def visit(self, node):
        method = getattr(self, f"visit_{node.type}", None)
        if method is not None:
            method(node)
        else:
            self.visit_generic(node)

    def visit_generic(self, node):
        for child in node.named_children:
            self.visit(child)

    def visit_block(self, node):
        for child in node.named_children:
            self.visit(child)

    def visit_expression_statement(self, node):
        text = self.get_text(node)
        expr = text.rstrip(';')
        deps = self.get_vars(expr)
        if self.current_cond:
            deps.append(self.current_cond)
        self.add_node(expr, deps)

    visit_local_variable_declaration = visit_expression_statement

    def visit_return_statement(self, node):
        text = self.get_text(node)
        expr = text[len('return'):].strip().rstrip(';')
        vars_ = self.get_vars(expr)
        deps = [self.current_cond] if self.current_cond else vars_
        self.add_node(expr or 'return', deps)

    def visit_if_statement(self, node):
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond)
        self.add_node(cond_text, self.get_vars(cond_text))
        prev = self.current_cond
        self.current_cond = cond_text
        cons = node.child_by_field_name('consequence')
        if cons.type == 'block':
            self.visit_block(cons)
        else:
            self.visit(cons)
        alt = node.child_by_field_name('alternative')
        if alt is not None:
            neg = f'not ({cond_text})'
            self.add_node(neg, self.get_vars(cond_text))
            self.current_cond = neg
            if alt.type == 'block':
                self.visit_block(alt)
            else:
                self.visit(alt)
        self.current_cond = prev

    def visit_while_statement(self, node):
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond)
        self.add_node(cond_text, self.get_vars(cond_text))
        prev = self.current_cond
        self.current_cond = cond_text
        body = node.child_by_field_name('body')
        if body.type == 'block':
            self.visit_block(body)
        else:
            self.visit(body)
        self.current_cond = prev

    def visit_for_statement(self, node):
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond) if cond else 'for'
        self.add_node(cond_text, self.get_vars(cond_text))
        prev = self.current_cond
        self.current_cond = cond_text
        body = node.child_by_field_name('body')
        if body.type == 'block':
            self.visit_block(body)
        else:
            self.visit(body)
        self.current_cond = prev

    visit_enhanced_for_statement = visit_for_statement

    # ------------------------------------------------------------------
    # Fallback parser utilities
    # ------------------------------------------------------------------
    class _FakeNode:
        def __init__(self, text: str, line: int, node_type: str = "expression_statement"):
            self.text = text.encode()
            self.type = node_type
            self.named_children = []
            self.start_point = (line, 0)

    class _FakeTree:
        def __init__(self, stmts: List[str]):
            self.root_node = DFGBuilder._FakeNode("root", 0, "block")
            self.root_node.named_children = [DFGBuilder._FakeNode(s, i) for i, s in enumerate(stmts)]

    def _fake_parse(self, stmts: List[str]):
        return self._FakeTree(stmts)

    # ------------------------------------------------------------------
    # tree-sitter based implementation
    # ------------------------------------------------------------------
    def build(self, name: str, tree, src: str, params: List[str] = None) -> DFG:
        self.nodes = []
        self.current_cond = None
        if params:
            for p in params:
                self.add_node(p)

        self.src = src
        root = tree.root_node
        method = None
        for child in root.named_children:
            if child.type == "method_declaration":
                method = child
                break

        body = method.child_by_field_name("body") if method else root
        if body.type == "block":
            self.visit_block(body)
        else:
            self.visit(body)
        return DFG(name, self.nodes)

    def build_from_src(self, name: str, src: str) -> DFG:
        if self.parser is not None:
            tree = self.parser.parse(bytes(src, "utf8"))
            params = []
            root = tree.root_node
            method = None
            for child in root.named_children:
                if child.type == "method_declaration":
                    method = child
                    break
            if method is not None:
                p_node = method.child_by_field_name("parameters")
                if p_node is not None:
                    for c in p_node.named_children:
                        if c.type == "formal_parameter":
                            name_node = c.child_by_field_name("name")
                            if name_node is not None:
                                params.append(self.get_text(name_node))
            return self.build(name, tree, src, params)

        # Fallback to regex-based splitting when parser is unavailable
        start_body = src.find("{")
        header = src[:start_body]
        end = src.rfind("}")
        body = src[start_body + 1:end]
        pattern = r"(?:if\s*\([^\)]+\)\s*\{?|else\s*\{?|while\s*\([^\)]+\)\s*\{?|for\s*\([^\)]+\)\s*\{?|case[^:]*:|default:|[^;{}]+;)"
        stmts = [part.strip() for part in re.findall(pattern, body)]

        params = []
        if "(" in header and ")" in header:
            param_list = header[header.find("(") + 1 : header.rfind(")")]
            for p in param_list.split(','):
                p = p.strip()
                if not p:
                    continue
                m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\])*$", p)
                if m:
                    params.append(m.group(1))

        tree = self._fake_parse(stmts)
        return self.build(name, tree, src, params)

    def build_from_file(self, name: str, filepath: str) -> DFG:
        with open(filepath, 'r') as src_file:
            src = src_file.read()
        return self.build_from_src(name, src)
