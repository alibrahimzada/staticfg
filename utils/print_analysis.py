import pydot
import re
import argparse
from collections import defaultdict, deque

from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_java as tsjava


class DataFlowAnalyzer:
    def __init__(self):
        self.variable_defs = defaultdict(list)  # variable -> [(node_id, statement)]
        self.variable_uses = defaultdict(list)  # variable -> [(node_id, statement)]

    def analyze_variable_usage(self, nodes, variables, mapping, parameters=None):
        """Analyze each node to find variable definitions and uses"""
        # Clear previous analysis
        self.variable_defs.clear()
        self.variable_uses.clear()

        # Remove duplicates from variables list while preserving order
        unique_variables = []
        seen = set()
        for var in variables:
            if var not in seen:
                unique_variables.append(var)
                seen.add(var)
        variables = unique_variables

        # Add parameter definitions at Node 0 if parameters exist
        if parameters:
            for param in parameters:
                if param in variables:
                    self.variable_defs[param].append((0, f"parameter: {param}"))

        for orig_node_id, label in nodes.items():
            # Get the remapped node ID
            remapped_node_id = mapping[orig_node_id]

            # Split label into individual statements
            statements = [stmt.strip() for stmt in label.split("\n") if stmt.strip()]

            for stmt in statements:
                # Skip function definitions and control flow headers
                if (
                    stmt.startswith("def ")
                    or stmt.startswith("for ")
                    or stmt.startswith("while ")
                    or stmt.startswith("if ")
                    or stmt.startswith("return ")
                    or stmt.startswith("print(")
                ):
                    # But check for variable uses in conditions and expressions
                    for var in variables:
                        if re.search(rf"\b{var}\b", stmt):
                            # Check if it's in a condition or expression (not a definition)
                            if not re.match(rf"^{var}\s*=", stmt):
                                # Avoid duplicates
                                if (remapped_node_id, stmt) not in self.variable_uses[var]:
                                    self.variable_uses[var].append((remapped_node_id, stmt))
                    continue

                # Find variable definitions and uses
                for var in variables:
                    # Check for direct assignment (definition)
                    if re.match(rf"^(?:\w+\s+)?{var}\s*=\s*", stmt):
                        if (remapped_node_id, stmt) not in self.variable_defs[var]:
                            self.variable_defs[var].append((remapped_node_id, stmt))

                    # Check for compound assignment (both def and use)
                    elif re.match(rf"^{var}\s*[+\-*/]=", stmt):
                        if (remapped_node_id, stmt) not in self.variable_defs[var]:
                            self.variable_defs[var].append((remapped_node_id, stmt))
                        if (remapped_node_id, stmt) not in self.variable_uses[var]:
                            self.variable_uses[var].append((remapped_node_id, stmt))

                    # Check for uses in right-hand side of assignments
                    elif "=" in stmt and re.search(rf"\b{var}\b", stmt.split("=", 1)[1]):
                        if (remapped_node_id, stmt) not in self.variable_uses[var]:
                            self.variable_uses[var].append((remapped_node_id, stmt))

                    # Check for other uses (function calls, expressions, etc.)
                    elif re.search(rf"\b{var}\b", stmt) and not re.match(rf"^{var}\s*=", stmt):
                        if (remapped_node_id, stmt) not in self.variable_uses[var]:
                            self.variable_uses[var].append((remapped_node_id, stmt))

    def find_paths_between_nodes(self, start_node, end_node, remapped_succs, max_depth=20):
        """Find all paths from start_node to end_node using BFS with remapped node IDs"""
        if start_node == end_node:
            return [[start_node]]

        paths = []
        queue = deque([(start_node, [start_node])])
        visited_paths = set()

        while queue:
            current_node, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current_node == end_node:
                path_tuple = tuple(path)
                if path_tuple not in visited_paths:
                    paths.append(path)
                    visited_paths.add(path_tuple)
                continue

            # Use remapped successors directly
            if current_node in remapped_succs:
                for neighbor, _ in remapped_succs[current_node]:
                    if neighbor not in path:  # Avoid cycles
                        new_path = path + [neighbor]
                        queue.append((neighbor, new_path))

        return paths

    def extract_dataflow_paths(self, variables, remapped_succs):
        """Extract data flow paths for each variable using remapped node IDs"""
        results = {}

        # Remove duplicates from variables list
        unique_variables = []
        seen = set()
        for var in variables:
            if var not in seen:
                unique_variables.append(var)
                seen.add(var)

        for var in unique_variables:
            results[var] = []
            defs = self.variable_defs[var]
            uses = self.variable_uses[var]

            # Find paths from each definition to each use
            for def_node, def_stmt in defs:
                for use_node, use_stmt in uses:
                    if def_node != use_node:  # Don't include same-node def-use
                        paths = self.find_paths_between_nodes(def_node, use_node, remapped_succs)
                        for path in paths:
                            # Avoid duplicate paths
                            path_info = {
                                "def": (def_node, def_stmt), 
                                "use": (use_node, use_stmt), 
                                "path": path
                            }
                            if path_info not in results[var]:
                                results[var].append(path_info)

        return results

    def print_dataflow_analysis(self, variables, succs, mapping, nodes, parameters=None, entry_orig=None):
        """Print data flow analysis results"""
        # Remove duplicates from variables list
        unique_variables = []
        seen = set()
        for var in variables:
            if var not in seen:
                unique_variables.append(var)
                seen.add(var)
        variables = unique_variables

        # Create remapped successors dict using new node IDs
        remapped_succs = {}
        for orig_node, successors in succs.items():
            new_node = mapping[orig_node]
            remapped_succs[new_node] = []
            for succ_orig, label in successors:
                succ_new = mapping[succ_orig]
                remapped_succs[new_node].append((succ_new, label))

        # Add Node 0 and Node 1 connections if parameters exist
        if parameters and entry_orig:
            # Node 0 connects to Node 1 (ENTRY)
            remapped_succs[0] = [(1, "")]
            # Node 1 (ENTRY) connects to all entry nodes of the CFG
            remapped_succs[1] = []
            for orig_entry in entry_orig:
                entry_node = mapping[orig_entry]
                remapped_succs[1].append((entry_node, ""))

        self.analyze_variable_usage(nodes, variables, mapping, parameters)
        paths = self.extract_dataflow_paths(variables, remapped_succs)

        print("=" * 60)
        print("DATA FLOW ANALYSIS")
        print("=" * 60)

        # Print variable definitions and uses summary
        print("\nVariable Definitions and Uses:")
        print("-" * 40)
        for var in variables:
            print(f"\nVariable: {var}")
            if self.variable_defs[var]:
                print(f"  Definitions ({len(self.variable_defs[var])}):")
                for node_id, stmt in self.variable_defs[var]:
                    print(f"    Node {node_id}: {stmt}")
            else:
                print("  Definitions: None")

            if self.variable_uses[var]:
                print(f"  Uses ({len(self.variable_uses[var])}):")
                for node_id, stmt in self.variable_uses[var]:
                    print(f"    Node {node_id}: {stmt}")
            else:
                print("  Uses: None")

        # Print data flow paths
        print(f"\n{'='*60}")
        print("DATA FLOW PATHS:")
        print("=" * 60)

        for var in variables:
            print(f"\nVariable: {var}")
            if not paths[var]:
                print("  No data flow paths found")
                continue

            for i, path_info in enumerate(paths[var], 1):
                def_node, def_stmt = path_info["def"]
                use_node, use_stmt = path_info["use"]
                path = path_info["path"]

                print(f"  Path {i}:")
                print(f"    Definition: Node {def_node} → {def_stmt}")
                print(f"    Use: Node {use_node} → {use_stmt}")
                print(f"    CFG Path: {' → '.join(map(str, path))}")
                print()


def parse_nodes_edges(graph):
    """
    Given a pydot Graph or Subgraph, return:
      - nodes: dict mapping original_node_id (str) → label (str) (preserving newlines)
      - edges: list of tuples (src_id, dst_id, edge_label)
    Only considers nodes and edges directly under this graph (ignores nested subgraphs).
    """
    nodes = {}
    for node in graph.get_nodes():
        name = node.get_name().strip('"')
        if not name.isdigit():
            continue
        raw_label = node.get_attributes().get("label", "")
        label = raw_label.strip('"').rstrip()
        nodes[name] = label

    edges = []
    for edge in graph.get_edges():
        src = edge.get_source().strip('"')
        dst = edge.get_destination().strip('"')
        if not (src.isdigit() and dst.isdigit()):
            continue
        raw_elabel = edge.get_attributes().get("label", "").strip('"')
        elabel = raw_elabel.replace("\n", " ").rstrip()
        edges.append((src, dst, elabel))

    return nodes, edges


def build_pred_succ(nodes, edges):
    preds = {nid: [] for nid in nodes}
    succs = {nid: [] for nid in nodes}
    for src, dst, elabel in edges:
        succs[src].append((dst, elabel))
        preds[dst].append((src, elabel))
    return preds, succs


def remap_node_ids(nodes, preds, parameters=None):
    """Remap node IDs starting from 2, with Node 0 for parameters and Node 1 for ENTRY"""
    # find originals with no predecessors
    entry_orig = [nid for nid, plist in preds.items() if not plist]
    if not entry_orig:
        entry_orig = [min(nodes.keys(), key=lambda x: int(x))]
    entry_orig = sorted(entry_orig, key=int)
    mapping = {}
    next_id = 2  # Start from 2 (Node 0 = parameters, Node 1 = ENTRY)
    for orig in sorted(nodes, key=int):
        mapping[orig] = next_id
        next_id += 1
    return mapping, entry_orig


def get_subgraph_label(graph):
    name = graph.get_name().strip('"')
    if name.startswith("cluster"):
        return name[len("cluster") :]
    return None


def pretty_print_cfg(nodes, preds, succs, mapping, entry_orig, header_label=None, parameters=None):
    if header_label:
        print(f"### CFG for {header_label} ###")

    # Print Node 0 (Parameters) if parameters exist
    if parameters:
        print("Node 0: PARAMETERS")
        for param in parameters:
            print(f"    parameter: {param}")
        print("    └─> Node 1: ENTRY")
        print()

    print("Node 1: ENTRY")
    for idx, orig in enumerate(entry_orig):
        arrow = "└─>" if idx == len(entry_orig) - 1 else "├─>"
        new_id = mapping[orig]
        lines = nodes[orig].split("\n")
        print(f"    {arrow} Node {new_id}: {lines[0]}")
        for extra in lines[1:]:
            print(f"        {extra}")
    print()

    new_to_orig = {new: orig for orig, new in mapping.items()}
    for new_id in sorted(new_to_orig):
        orig = new_to_orig[new_id]
        lines = nodes[orig].split("\n")
        print(f"Node {new_id}:")
        for ln in lines:
            print(f"    {ln}")
        children = succs.get(orig, [])
        if children:
            for cidx, (sorig, el) in enumerate(children):
                arrow = "└─>" if cidx == len(children) - 1 else "├─>"
                sid = mapping[sorig]
                if el:
                    print(f'    {arrow} Node {sid} [label="{el}"]:')
                else:
                    print(f"    {arrow} Node {sid}:")
                for sl in nodes[sorig].split("\n"):
                    print(f"        {sl}")
        print()
    print("-" * 40)


def process_graph_recursively(graph, do_dataflow=False, variables=None):
    label = get_subgraph_label(graph)
    nodes, edges = parse_nodes_edges(graph)
    if nodes:
        preds, succs = build_pred_succ(nodes, edges)

        # Extract parameters from variables dict
        parameters = variables.get("parameters", []) if variables else []
        all_vars = []
        if variables:
            all_vars.extend(variables.get("local_vars", []))
            all_vars.extend(variables.get("parameters", []))

        mapping, entry_orig = remap_node_ids(nodes, preds, parameters)
        pretty_print_cfg(nodes, preds, succs, mapping, entry_orig, header_label=label, parameters=parameters)

        # Add data flow analysis if requested
        if do_dataflow and all_vars:
            analyzer = DataFlowAnalyzer()
            analyzer.print_dataflow_analysis(all_vars, succs, mapping, nodes, parameters, entry_orig)

    for sub in graph.get_subgraphs():
        process_graph_recursively(sub, do_dataflow, variables)


def get_java_variables(root):
    variables = {"local_vars": [], "parameters": []}

    def extract_parameters(node):
        if node.type == "formal_parameter":
            param_name = node.child_by_field_name("name")
            if param_name:
                variables["parameters"].append(param_name.text.decode("utf-8"))
        for child in node.children:
            extract_parameters(child)

    def extract_local_vars(node):
        if node.type == "variable_declarator":
            var_name = node.child_by_field_name("name")
            if var_name:
                variables["local_vars"].append(var_name.text.decode("utf-8"))
        for child in node.children:
            extract_local_vars(child)

    extract_parameters(root)
    extract_local_vars(root)

    return variables


def get_python_variables(root):
    variables = {"local_vars": [], "parameters": []}

    def extract_parameters(node):
        if node.type == "parameters":
            for param in node.named_children:
                # simple un-annotated param:    def f(x, y):
                if param.type == "identifier":
                    variables["parameters"].append(param.text.decode("utf-8"))

                # parameters with default or annotation:
                #   def f(a=1, b: int, *args, **kwargs):
                elif param.type in (
                    "default_parameter",
                    "typed_parameter",
                    "typed_default_parameter",
                    "list_splat_pattern",  # for *args
                    "dictionary_splat_pattern",  # for **kwargs
                ):
                    # the identifier is always the first named child
                    for child in param.named_children:
                        if child.type == "identifier":
                            variables["parameters"].append(child.text.decode("utf-8"))
                            break
            # no need to recurse into the inside of parameters
            return

        for child in node.children:
            extract_parameters(child)

    def extract_local_vars(node):
        if node.type in ["assignment", "augmented_assignment"]:
            var_name = node.child_by_field_name("left")
            if var_name:
                variables["local_vars"].append(var_name.text.decode("utf-8"))

        for child in node.children:
            extract_local_vars(child)

    extract_parameters(root)
    extract_local_vars(root)

    return variables


def get_variables_from_source(args):

    LANGUAGE = None
    if args.language == "java":
        LANGUAGE = Language(tsjava.language())
    elif args.language == "python":
        LANGUAGE = Language(tspython.language())

    if LANGUAGE is None:
        raise ValueError("Unsupported language. Use 'java' or 'python'.")

    parser = Parser(LANGUAGE)

    source_code = ""
    with open(args.source_file, "r") as f:
        source_code = f.read().encode("utf-8")

    tree = parser.parse(source_code)
    root = tree.root_node

    variables = {"local_vars": [], "parameters": []}

    if args.language == "java":
        variables = get_java_variables(root)

    elif args.language == "python":
        variables = get_python_variables(root)

    return variables


def main():
    parser = argparse.ArgumentParser(description="CFG and DFG Printer")
    parser.add_argument("--dot_file", help="Path to the DOT file containing the CFG")
    parser.add_argument("--source_file", help="Path to the source file")
    parser.add_argument("--language", default="python", help="Programming language for parsing")
    parser.add_argument("--dataflow", action="store_true", help="Enable data flow analysis")
    args = parser.parse_args()

    variables = get_variables_from_source(args)

    with open(args.dot_file, "r") as f:
        dot_data = f.read()

    graphs = pydot.graph_from_dot_data(dot_data)

    if not graphs:
        return

    top = graphs[0]
    subs = top.get_subgraphs()

    if subs:
        for sub in subs:
            process_graph_recursively(sub, args.dataflow, variables)
    else:
        process_graph_recursively(top, args.dataflow, variables)


if __name__ == "__main__":
    main()
