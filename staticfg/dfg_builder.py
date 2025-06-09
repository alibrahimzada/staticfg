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
        # Track separate paths for each variable instead of mixing them
        self.track_separately = True

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
        
        # Add this block's occurrences to the path
        block_occs = self._block_occurrences(block)
        updated_path = list(path)
        
        # Group occurrences by variable name
        for name, lineno in block_occs:
            # Only add to path if we're tracking this variable
            # or if path is empty (starting a new variable path)
            if not path or name == path[0][0]:
                updated_path.append((name, lineno))
            
        if block in self.cfg.finalblocks:
            # Only add paths that have occurrences
            if updated_path:
                results.append(updated_path)
        else:
            for exit_ in block.exits:
                self._dfs(exit_.target, updated_path, set(visited), results)

    def build_paths(self) -> List[List[Tuple[str, int]]]:
        results: List[List[Tuple[str, int]]] = []
        
        # Initialize separate paths for each variable if requested
        if self.track_separately:
            # Group start occurrences by variable name
            var_paths = {}
            for name, lineno in self.start_occurrences:
                if name not in var_paths:
                    var_paths[name] = []
                var_paths[name].append((name, lineno))
                
            # Start paths with individual variables
            for _, occs in var_paths.items():
                self._dfs(self.cfg.entryblock, occs, set(), results)
                
            # Also start paths with locally defined variables (not parameters)
            self._dfs(self.cfg.entryblock, [], set(), results)
        else:
            # Original behavior: all variables in a single path
            self._dfs(self.cfg.entryblock, list(self.start_occurrences), set(), results)
        
        # Filter to only keep unique paths and sort them by variable
        unique = []
        for p in results:
            # Filter out empty paths
            if p and p not in unique:
                unique.append(p)
                
        return unique

    def write_paths(self, filepath: str, mode: str = 'w', header: Optional[str] = None):
        paths = self.build_paths()
        
        # Group paths by variable name for cleaner output
        var_paths = {}
        for path in paths:
            if not path:
                continue
                
            # Get the variable name for this path
            var_name = path[0][0] if path else "unknown"
            
            # Store path by variable name
            if var_name not in var_paths:
                var_paths[var_name] = []
            var_paths[var_name].append(path)
        
        with open(filepath, mode) as f:
            if header:
                f.write(f"{header}\n")
                
            path_idx = 1
            # Output paths grouped by variable
            for var_name, var_specific_paths in var_paths.items():
                f.write(f"Variable: {var_name}\n")
                for path in var_specific_paths:
                    parts = [f"({name}, {lineno})" for name, lineno in path]
                    f.write(f"  Path {path_idx}: " + " -> ".join(parts) + "\n")
                    path_idx += 1
                f.write("\n")


