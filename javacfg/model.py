"""Control flow graph classes for Java code."""

import graphviz as gv

class Block:
    __slots__ = ["id", "statements", "func_calls", "predecessors", "exits"]

    def __init__(self, id):
        self.id = id
        self.statements = []
        self.func_calls = []
        self.predecessors = []
        self.exits = []

    def __str__(self):
        if self.statements:
            return f"block:{self.id}@{self.at()}"
        return f"empty block:{self.id}"

    def __repr__(self):
        txt = f"{str(self)} with {len(self.exits)} exits"
        if self.statements:
            txt += ", body=[" + ", ".join([s.type for s in self.statements]) + "]"
        return txt

    def at(self):
        if self.statements:
            return self.statements[0].start_point[0] + 1
        return None

    def is_empty(self):
        return len(self.statements) == 0

    def get_source(self):
        src = ""
        for stmt in self.statements:
            text = stmt.text.decode()
            if stmt.type in (
                "if_statement",
                "while_statement",
                "for_statement",
                "enhanced_for_statement",
                "switch_expression",
                "switch_statement",
            ):
                src += text.splitlines()[0] + "\n"
            else:
                src += text + "\n"
        return src

    def get_calls(self):
        txt = ""
        for func in self.func_calls:
            txt += func + "\n"
        return txt


class Link:
    __slots__ = ["source", "target", "exitcase"]

    def __init__(self, source, target, exitcase=None):
        assert isinstance(source, Block)
        assert isinstance(target, Block)
        self.source = source
        self.target = target
        self.exitcase = exitcase

    def __str__(self):
        return f"link from {self.source} to {self.target}"

    def __repr__(self):
        if self.exitcase is not None:
            return f"{self}, with exitcase {self.exitcase}"
        return str(self)

    def get_exitcase(self):
        return self.exitcase or ""


class CFG:
    def __init__(self, name, asynchr=False):
        assert isinstance(name, str)
        self.name = name
        self.asynchr = asynchr
        self.entryblock = None
        self.finalblocks = []
        self.functioncfgs = {}

    def __str__(self):
        return f"CFG for {self.name}"

    def __iter__(self):
        visited = set()
        to_visit = [self.entryblock]
        while to_visit:
            block = to_visit.pop(0)
            visited.add(block)
            for exit_ in block.exits:
                if exit_.target in visited or exit_.target in to_visit:
                    continue
                to_visit.append(exit_.target)
            yield block
        for subcfg in self.functioncfgs.values():
            yield from subcfg

    def _visit_blocks(self, graph, block, visited=None, calls=True):
        if visited is None:
            visited = []
        if block.id in visited:
            return

        nodelabel = block.get_source()
        graph.node(str(block.id), label=nodelabel)
        visited.append(block.id)

        if calls and block.func_calls:
            calls_node = f"{block.id}_calls"
            calls_label = block.get_calls().strip()
            graph.node(calls_node, label=calls_label, _attributes={"shape": "box"})
            graph.edge(str(block.id), calls_node, label="calls", _attributes={"style": "dashed"})

        for exit in block.exits:
            self._visit_blocks(graph, exit.target, visited, calls=calls)
            edgelabel = exit.get_exitcase().strip()
            graph.edge(str(block.id), str(exit.target.id), label=edgelabel)

    def _build_visual(self, format="pdf", calls=True):
        graph = gv.Digraph(name="cluster" + self.name, format=format, graph_attr={"label": self.name})
        self._visit_blocks(graph, self.entryblock, visited=[], calls=calls)

        for subcfg in self.functioncfgs:
            subgraph = self.functioncfgs[subcfg]._build_visual(format=format, calls=calls)
            graph.subgraph(subgraph)

        return graph

    def build_visual(self, filepath, format, calls=True, show=True):
        graph = self._build_visual(format, calls)
        graph.render(filepath, view=show)
