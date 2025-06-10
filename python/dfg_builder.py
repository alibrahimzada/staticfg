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
            for child in n.body:
                self.visit(child)

        def visit_While(self, n: ast.While) -> None:
            self.visit(n.test)
            for child in n.body:
                self.visit(child)

        def visit_Match(self, n: ast.Match) -> None:
            self.visit(n.subject)
            for case in n.cases:
                self.visit(case.pattern)
                if case.guard is not None:
                    self.visit(case.guard)

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

        def collect_defined(fn_node: ast.FunctionDef) -> List[str]:
            names = set()
            class Visitor(ast.NodeVisitor):
                def visit_Name(self, n: ast.Name) -> None:
                    if isinstance(n.ctx, ast.Store):
                        names.add(n.id)

                def visit_FunctionDef(self, fn: ast.FunctionDef) -> None:
                    # Do not traverse into nested function bodies or record
                    # their parameters for the parent scope
                    names.add(fn.name)

                def visit_AsyncFunctionDef(self, fn: ast.AsyncFunctionDef) -> None:
                    names.add(fn.name)

            visitor = Visitor()
            for stmt in fn_node.body:
                visitor.visit(stmt)
            return list(names)

        def process_function(fn: ast.FunctionDef) -> None:
            param_names = [arg.arg for arg in fn.args.args]
            params[fn.name] = (fn.lineno, param_names)
            defined = collect_defined(fn)
            var_sets[fn.name] = list(dict.fromkeys(param_names + defined))
            for child in fn.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    process_function(child)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                process_function(node)

        cfg = CFGBuilder().build_from_file(name, filepath)
        result: Dict[str, Dict[str, List[str]]] = {}
        def build_recursive(func_name: str, sub: CFG) -> None:
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
            for sub_name, sub_cfg in sub.functioncfgs.items():
                build_recursive(sub_name, sub_cfg)

        for func_name, sub in cfg.functioncfgs.items():
            build_recursive(func_name, sub)

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
        return dfg

    def pretty_print(self, dfg: Dict[str, Dict[str, List[str]]]) -> None:
        already_printed = set()
        for func_name, vars_ in dfg.items():
            print(f"### DFG for Function {func_name} ###")
            for var, paths in vars_.items():
                print(f"Variable: {var}")
                for i, path in enumerate(paths, 1):
                    if (func_name, var, path) in already_printed:
                        continue
                    already_printed.add((func_name, var, path))
                    print(f"  Path {i}: {path}")
                print()
            print("-" * 40)