import ast
from typing import List, Dict, Tuple

from .cfg_builder import CFGBuilder
from .model import CFG, Block


def _collect_names(node: ast.AST, vars_to_track: List[str] = None) -> List[Tuple[str, int]]:
    """Return (name, lineno) pairs for variables in *node*.

    If *vars_to_track* is provided, only occurrences of those variable names are
    returned.
    """

    names: List[Tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def visit_Name(self, n: ast.Name) -> None:
            names.append((n.id, n.lineno))

        def visit_FunctionDef(self, n: ast.FunctionDef) -> None:
            for arg in n.args.args:
                names.append((arg.arg, n.lineno))
            # Do not traverse into nested function bodies

        def visit_AsyncFunctionDef(self, n: ast.AsyncFunctionDef) -> None:
            for arg in n.args.args:
                names.append((arg.arg, n.lineno))

        def visit_If(self, n: ast.If) -> None:
            self.visit(n.test)

        def visit_For(self, n: ast.For) -> None:
            self.visit(n.target)
            self.visit(n.iter)

        def visit_While(self, n: ast.While) -> None:
            self.visit(n.test)

    Visitor().visit(node)
    # Remove duplicates while preserving order by line number
    seen = set()
    unique: List[Tuple[str, int]] = []
    for name in sorted(names, key=lambda x: x[1]):
        if name not in seen:
            unique.append(name)
            seen.add(name)
    if vars_to_track is not None:
        unique = [v for v in unique if v[0] in vars_to_track]
    return unique


def _block_occurrences(block: Block, vars_to_track: List[str]) -> List[Tuple[str, int]]:
    """Return variable occurrences for all statements in *block*."""
    occs: List[Tuple[str, int]] = []
    for stmt in block.statements:
        occs.extend(_collect_names(stmt, vars_to_track))
    return occs


def _enumerate_paths(cfg: CFG) -> List[List[Block]]:
    """Enumerate all simple paths from entry to each final block."""
    paths: List[List[Block]] = []
    visited: List[Block] = []

    def dfs(block: Block, current: List[Block]) -> None:
        current.append(block)
        if block in cfg.finalblocks or not block.exits:
            paths.append(list(current))
        else:
            for exit_ in block.exits:
                if exit_.target not in current:
                    dfs(exit_.target, current)
        current.pop()

    dfs(cfg.entryblock, [])
    return paths


class DFGBuilder:
    """Simple data flow path extractor based on a CFG."""

    def build_from_file(self, name: str, filepath: str) -> Dict[str, Dict[str, List[str]]]:
        """Build the DFG of all functions in the file located at *filepath*."""
        with open(filepath, "r") as f:
            src = f.read()
        tree = ast.parse(src, mode="exec")

        params: Dict[str, Tuple[int, List[str]]] = {}
        var_sets: Dict[str, List[str]] = {}

        def collect_defined(node: ast.AST) -> List[str]:
            names = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    names.add(n.id)
            names.update(arg.arg for arg in node.args.args)
            return list(names)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                param_names = [arg.arg for arg in node.args.args]
                params[node.name] = (node.lineno, param_names)
                var_sets[node.name] = collect_defined(node)

        cfg = CFGBuilder().build_from_file(name, filepath)
        result: Dict[str, Dict[str, List[str]]] = {}
        for func_name, sub in cfg.functioncfgs.items():
            vars_to_track = var_sets.get(func_name, [])
            func_dfg = self._build(sub, vars_to_track)
            if func_name in params:
                line, param_names = params[func_name]
                for param in param_names:
                    if param in func_dfg:
                        func_dfg[param] = [f"({param}, {line}) -> " + p for p in func_dfg[param]]
                    else:
                        func_dfg[param] = [f"({param}, {line})"]
            result[func_name] = func_dfg
        return result

    def _build(self, cfg: CFG, vars_to_track: List[str]) -> Dict[str, List[str]]:
        dfg: Dict[str, List[str]] = {}
        paths = _enumerate_paths(cfg)
        for path in paths:
            per_var: Dict[str, List[Tuple[str, int]]] = {}
            for block in path:
                for var, line in _block_occurrences(block, vars_to_track):
                    seq = per_var.setdefault(var, [])
                    if seq and seq[-1][1] == line:
                        continue
                    seq.append((var, line))
            for var, occs in per_var.items():
                path_txt = " -> ".join(f"({v}, {ln})" for v, ln in occs)
                dfg.setdefault(var, []).append(path_txt)
        # Recurse into nested function CFGs if any
        for sub in cfg.functioncfgs.values():
            sub_dfg = self._build(sub, vars_to_track)
            for var, paths in sub_dfg.items():
                dfg.setdefault(var, []).extend(paths)
        return dfg

    def pretty_print(self, dfg: Dict[str, Dict[str, List[str]]]) -> None:
        already_printed = set()
        for func_name, vars_ in dfg.items():
            print(f"Function {func_name}")
            for var, paths in vars_.items():
                print(f"Variable: {var}")
                for i, path in enumerate(paths, 1):
                    if (func_name, var, path) in already_printed:
                        continue
                    already_printed.add((func_name, var, path))
                    print(f"  Path {i}: {path}")
                print()