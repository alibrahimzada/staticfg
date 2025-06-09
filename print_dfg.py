import sys
import pydot


def parse_nodes_edges(graph):
    """Return dict of node name -> label and list of edges."""
    nodes = {}
    for node in graph.get_nodes():
        name = node.get_name().strip('"')
        if name.lower() in {'node', 'graph', 'edge'}:
            continue
        raw_label = node.get_attributes().get('label', '')
        label = raw_label.strip('"').rstrip()
        nodes[name] = label or name

    edges = []
    for edge in graph.get_edges():
        src = edge.get_source().strip('"')
        dst = edge.get_destination().strip('"')
        raw_elabel = edge.get_attributes().get('label', '')
        elabel = raw_elabel.replace('\n', ' ').strip('"').rstrip()
        edges.append((src, dst, elabel))
    return nodes, edges

def build_pred_succ(nodes, edges):
    preds = {nid: [] for nid in nodes}
    succs = {nid: [] for nid in nodes}
    for src, dst, elabel in edges:
        if src not in succs:
            continue
        succs[src].append((dst, elabel))
        if dst in preds:
            preds[dst].append((src, elabel))
    return preds, succs


def remap_node_ids(nodes, preds):
    entry_orig = sorted([nid for nid, plist in preds.items() if not plist])
    mapping = {}
    next_id = 2
    for orig in sorted(nodes.keys()):
        mapping[orig] = next_id
        next_id += 1
    return mapping, entry_orig

def pretty_print_dfg(nodes, preds, succs, mapping, entry_orig, header_label=None):
    if header_label:
        print(f"### DFG for {header_label} ###")
    print("Node 1: ENTRY")
    last_arrow = "\u2514\u2500>"
    mid_arrow = "\u251c\u2500>"
    for idx, orig in enumerate(entry_orig):
        arrow = last_arrow if idx == len(entry_orig) - 1 else mid_arrow
        new_id = mapping[orig]
        lines = nodes[orig].split('\n')
        print(f"    {arrow} Node {new_id}: {lines[0]}")
        for extra in lines[1:]:
            print(f"        {extra}")
    print()
    new_to_orig = {new: orig for orig, new in mapping.items()}
    for new_id in sorted(new_to_orig):
        orig = new_to_orig[new_id]
        lines = nodes[orig].split('\n')
        print(f"Node {new_id}:")
        for ln in lines:
            print(f"    {ln}")
        children = succs.get(orig, [])
        if children:
            for cidx, (sorig, el) in enumerate(children):
                arrow = last_arrow if cidx == len(children) - 1 else mid_arrow
                sid = mapping.get(sorig)
                if sid is None:
                    continue
                if el:
                    print(f"    {arrow} Node {sid} [label=\"{el}\"]:")
                else:
                    print(f"    {arrow} Node {sid}:")
                for sl in nodes[sorig].split('\n'):
                    print(f"        {sl}")
        print()
    print('-' * 40)

def get_subgraph_label(graph):
    name = graph.get_name().strip('"')
    if name.startswith("cluster"):
        return name[len("cluster"):]
    return None


def process_graph_recursively(graph):
    label = get_subgraph_label(graph)
    nodes, edges = parse_nodes_edges(graph)
    if nodes:
        preds, succs = build_pred_succ(nodes, edges)
        mapping, entry_orig = remap_node_ids(nodes, preds)
        pretty_print_dfg(nodes, preds, succs, mapping, entry_orig, header_label=label)
    for sub in graph.get_subgraphs():
        process_graph_recursively(sub)


def main():
    dot_data = sys.stdin.read()
    graphs = pydot.graph_from_dot_data(dot_data)
    if not graphs:
        return
    top = graphs[0]
    subs = top.get_subgraphs()
    if subs:
        for sub in subs:
            process_graph_recursively(sub)
    else:
        process_graph_recursively(top)


if __name__ == "__main__":
    main()
