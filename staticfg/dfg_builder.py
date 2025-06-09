import ast
from typing import List, Tuple


class _VarVisitor(ast.NodeVisitor):
    def __init__(self):
        self.occurrences: List[Tuple[str, int]] = []

    def visit_Name(self, node: ast.Name):
        if hasattr(node, 'lineno'):
            self.occurrences.append((node.id, node.lineno))
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg):
        if hasattr(node, 'lineno'):
            self.occurrences.append((node.arg, node.lineno))
        self.generic_visit(node)


def _var_occurrences(node: ast.AST) -> List[Tuple[str, int]]:
    visitor = _VarVisitor()
    visitor.visit(node)
    return visitor.occurrences


class DFGBuilder:
    """Simple data flow path builder for Python CFGs."""

    def __init__(self, cfg):
        self.cfg = cfg

    def _block_occurrences(self, block) -> List[Tuple[str, int]]:
        occs: List[Tuple[str, int]] = []
        for stmt in block.statements:
            occs.extend(_var_occurrences(stmt))
        return occs

    def _dfs(self, block, path, visited, results):
        if block in visited:
            return
        visited.add(block)
        path = path + self._block_occurrences(block)
        if block in self.cfg.finalblocks:
            results.append(path)
        else:
            for exit_ in block.exits:
                self._dfs(exit_.target, list(path), set(visited), results)

    def build_paths(self) -> List[List[Tuple[str, int]]]:
        results: List[List[Tuple[str, int]]] = []
        self._dfs(self.cfg.entryblock, [], set(), results)
        return results

    def write_paths(self, filepath: str):
        paths = self.build_paths()
        with open(filepath, 'w') as f:
            for idx, path in enumerate(paths, 1):
                parts = [f"({name}, {lineno})" for name, lineno in path]
                f.write(f"Path {idx}: " + " -> ".join(parts) + "\n")


