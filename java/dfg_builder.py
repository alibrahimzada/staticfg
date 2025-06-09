from typing import List, Tuple, Optional, Set, Dict
import re


class _VarVisitor:
    """Variable visitor for Java statements."""
    
    def __init__(self):
        self.occurrences: List[Tuple[str, int]] = []
        # Regex patterns for variable references in statements
        self.var_pattern = re.compile(r'\b([a-zA-Z_]\w*)\b')
        # Pattern to find string literals
        self.string_literal_pattern = re.compile(r'"([^"]*)"')
        # Pattern to find single-line comments
        self.comment_pattern = re.compile(r'//.*$', re.MULTILINE)
        # Pattern to find multi-line comments
        self.multiline_comment_pattern = re.compile(r'/\*.*?\*/', re.DOTALL)
        # Skip these keywords in variable detection
        self.keywords = {
            'if', 'else', 'while', 'for', 'switch', 'case', 'default',
            'return', 'break', 'continue', 'new', 'this', 'super',
            'true', 'false', 'null', 'public', 'private', 'protected',
            'static', 'final', 'void', 'int', 'double', 'float', 'boolean',
            'char', 'byte', 'short', 'long', 'String'
        }
    
    def visit(self, node, lineno: int):
        """Extract variable occurrences from a statement node."""
        if hasattr(node, 'text'):
            text = node.text.decode()
            
            # Remove comments before processing
            # First remove single line comments
            text = self.comment_pattern.sub('', text)
            # Then remove multi-line comments
            text = self.multiline_comment_pattern.sub('', text)
            
            # Find all string literals to exclude them
            string_literals = set()
            for literal_match in self.string_literal_pattern.finditer(text):
                string_literals.add(literal_match.group(1))
            
            # Find all variable-like identifiers
            matches = self.var_pattern.findall(text)
            for match in matches:
                # Skip keywords and string literals
                if match not in self.keywords and match not in string_literals:
                    # Also check if it appears in a return statement with quotes
                    if not (match in text and f'return "{match}"' in text):
                        self.occurrences.append((match, lineno))


def _var_occurrences(node) -> List[Tuple[str, int]]:
    """Extract variable occurrences from an AST node."""
    visitor = _VarVisitor()
    if hasattr(node, 'start_point'):
        lineno = node.start_point[0] + 1  # Convert to 1-based line number
        visitor.visit(node, lineno)
    return visitor.occurrences


def _stmt_occurrences(stmt) -> List[Tuple[str, int]]:
    """Extract variable occurrences from a single statement."""
    # For statements like if/while/for, we need to be more precise about where variables appear
    if hasattr(stmt, 'type'):
        if stmt.type in ('if_statement', 'while_statement', 'for_statement'):
            # For control statements, only consider variables in the condition
            # Not in the entire statement which would include all branches
            occurrences = []
            if hasattr(stmt, 'child_by_field_name'):
                condition = stmt.child_by_field_name('condition')
                if condition:
                    return _var_occurrences(condition)
            return occurrences
        
        # For local variable declarations, extract only the variable name
        elif stmt.type == 'local_variable_declaration':
            occurrences = []
            # This is a simplified approach - in a real implementation we'd need to 
            # more carefully parse the declaration to extract just the variable name
            var_data = _var_occurrences(stmt)
            # Filter out type names which are often capitalized
            var_data = [(name, line) for name, line in var_data 
                        if not (name[0].isupper() and name not in ('Integer', 'String', 'Boolean'))]
            return var_data
    
    # For other statements, process normally
    return _var_occurrences(stmt)


class DFGBuilder:
    """Data flow graph builder for Java CFGs.
    
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
        """Extract variable occurrences from a block."""
        occs: List[Tuple[str, int]] = []
        for stmt in block.statements:
            for name, lineno in _stmt_occurrences(stmt):
                if self.names is None or name in self.names:
                    entry = (name, lineno)
                    if entry not in occs:
                        occs.append(entry)
        return occs
    
    def _dfs(self, block, path, visited: Set, results: List):
        """Depth-first search to build data flow paths."""
        if block in visited:
            return
        visited.add(block)
        
        # Add this block's occurrences to the path
        block_occs = self._block_occurrences(block)
        updated_path = list(path)
        
        # Add occurrences to path, but only for the variable we're tracking
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
        """Build all data flow paths through the CFG."""
        results: List[List[Tuple[str, int]]] = []
        
        # Initialize separate paths for each variable if requested
        if self.track_separately:
            # Group start occurrences by variable name
            var_paths: Dict[str, List[Tuple[str, int]]] = {}
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
        """Write data flow paths to a file.
        
        Parameters
        ----------
        filepath : str
            Path to the output file.
        mode : str, optional
            File open mode, by default 'w'.
        header : str, optional
            Optional header to write at the top of the file.
        """
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
