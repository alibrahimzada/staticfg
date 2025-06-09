import ast
from typing import List, Tuple, Optional


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


def _stmt_occurrences(stmt: ast.AST) -> List[Tuple[str, int]]:
    """Return occurrences for a single statement without descending into child statements."""
    if isinstance(stmt, ast.If):
        return _var_occurrences(stmt.test)
    return _var_occurrences(stmt)


class DFGBuilder:
    """Simple data flow path builder for Python CFGs.

    Parameters
    ----------
    cfg : CFG
        The control flow graph from which to compute data flow paths.
    start_occurrences : list[tuple[str, int]], optional
        Starting occurrences to prepend to every path. Usually the function
        parameters.
    names : list[str] | set[str] | None, optional
        Restrict recorded occurrences to the specified variable names. When
        ``None`` all variable names are kept.
    """

    def __init__(self, cfg, start_occurrences=None, names=None):
        self.cfg = cfg
        self.start_occurrences = start_occurrences or []
        self.names = set(names) if names is not None else None

    """Simple data flow path builder for Python CFGs."""

    def __init__(self, cfg, start_occurrences=None):
        self.cfg = cfg
        self.start_occurrences = start_occurrences or []

    def _block_occurrences(self, block) -> List[Tuple[str, int]]:
        occs: List[Tuple[str, int]] = []
        for stmt in block.statements:
            for name, lineno in _stmt_occurrences(stmt):
                if self.names is None or name in self.names:
                    entry = (name, lineno)
                    if entry not in occs:
                        occs.append(entry)
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
        self._dfs(self.cfg.entryblock, list(self.start_occurrences), set(), results)
        unique = []
        for p in results:
            if p not in unique:
                unique.append(p)
        return unique

    def write_paths(self, filepath: str, mode: str = 'w', header: Optional[str] = None):
        paths = self.build_paths()
        with open(filepath, mode) as f:
            if header:
                f.write(f"{header}\n")
            for idx, path in enumerate(paths, 1):
                parts = [f"({name}, {lineno})" for name, lineno in path]
                f.write(f"Path {idx}: " + " -> ".join(parts) + "\n")


