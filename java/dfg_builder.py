import re
from typing import List, Dict, Tuple

from .cfg_builder import CFGBuilder
from .model import CFG, Block

JAVA_KEYWORDS = {
    'abstract', 'continue', 'for', 'new', 'switch', 'assert', 'default', 'goto', 'package',
    'synchronized', 'boolean', 'do', 'if', 'private', 'this', 'break', 'double',
    'implements', 'protected', 'throw', 'byte', 'else', 'import', 'public', 'throws',
    'case', 'enum', 'instanceof', 'return', 'transient', 'catch', 'extends', 'int',
    'short', 'try', 'char', 'final', 'interface', 'static', 'void', 'class', 'finally',
    'long', 'strictfp', 'volatile', 'const', 'float', 'native', 'super', 'while',
    'true', 'false', 'null'
}


def _collect_names(node, vars_to_track: List[str] = None) -> List[Tuple[str, int]]:
    """Return (name, lineno) pairs for variables appearing in *node* text."""
    text = node.text.decode() if hasattr(node, 'text') else str(node)
    line = node.start_point[0] + 1 if hasattr(node, 'start_point') else 0
    # Strip string literals to avoid capturing words in them
    text = re.sub(r'".*?"', '', text)
    tokens = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text)
    seen = set()
    names: List[Tuple[str, int]] = []
    for tok in tokens:
        if tok in JAVA_KEYWORDS:
            continue
        if vars_to_track is not None and tok not in vars_to_track:
            continue
        if tok not in seen:
            names.append((tok, line))
            seen.add(tok)
    return names


def _block_occurrences(block: Block, vars_to_track: List[str]) -> List[Tuple[str, int]]:
    occs: List[Tuple[str, int]] = []
    for stmt in block.statements:
        occs.extend(_collect_names(stmt, vars_to_track))
    return occs


def _enumerate_paths(cfg: CFG) -> List[List[Block]]:
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
    """Simple data flow path extractor based on a CFG for Java code."""

    def build_from_file(self, name: str, filepath: str) -> Dict[str, Dict[str, List[str]]]:
        with open(filepath, 'r') as f:
            src = f.read()

        method_match = re.search(r'(\w+)\s*\(([^)]*)\)\s*{', src)
        if method_match:
            func_name = method_match.group(1)
            method_line = src[:method_match.start()].count('\n') + 1
            param_str = method_match.group(2)
            param_names = []
            for param in param_str.split(','):
                param = param.strip()
                if not param:
                    continue
                name_part = param.split()[-1]
                name_part = name_part.split('[')[0]
                param_names.append(name_part)
        else:
            func_name = name
            method_line = 1
            param_names = []

        var_names = set(param_names)
        assign_pattern = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*[+\-*/]?=')
        for m in assign_pattern.finditer(src):
            var_names.add(m.group(1))

        cfg = CFGBuilder().build_from_file(name, filepath)
        vars_to_track = list(var_names)
        dfg = self._build(cfg, vars_to_track)
        result = {func_name: dfg}

        if param_names:
            for param in param_names:
                if param in dfg:
                    dfg[param] = [f'({param}, {method_line}) -> ' + p for p in dfg[param]]
                else:
                    dfg[param] = [f'({param}, {method_line})']
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
                path_txt = ' -> '.join(f'({v}, {ln})' for v, ln in occs)
                dfg.setdefault(var, []).append(path_txt)
        return dfg

    def pretty_print(self, dfg: Dict[str, Dict[str, List[str]]] | Dict[str, List[str]]) -> None:
        for func_name, vars_ in dfg.items():
            print(f'### DFG for Function {func_name} ###')
            for var, paths in vars_.items():
                print(f'Variable: {var}')
                for i, path in enumerate(paths, 1):
                    print(f'  Path {i}: {path}')
                print()
            print('-' * 40)