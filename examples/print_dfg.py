#!/usr/bin/env python3
"""Utility script to output a textual representation of a data flow graph."""

import argparse
from staticfg.dfg_builder import DFGBuilder

parser = argparse.ArgumentParser(description="Generate the data flow graph of a Python program")
parser.add_argument("input_file", help="Path to the Python source file")
parser.add_argument("--visual", dest="visual", help="Optional output path for a visual graph (without extension)")
args = parser.parse_args()

name = args.input_file.split('/')[-1]
dfg = DFGBuilder().build_from_file(name, args.input_file)

print(f"### DFG for {name} ###")
print("DFG_NODES:")
for node in dfg.nodes:
    dep = f" (depends_on: {', '.join(node.depends_on)})" if node.depends_on else ""
    print(f"- {node.name}{dep}")

print("\nDFG_PATHS:")
edges = {}
for node in dfg.nodes:
    for dep in node.depends_on:
        edges.setdefault(dep, []).append(node.name)

def dfs(start, path):
    if start not in edges:
        print(" → ".join(path))
        return
    for nxt in edges[start]:
        dfs(nxt, path + [nxt])

for node in [n.name for n in dfg.nodes if not n.depends_on]:
    dfs(node, [node])

if args.visual:
    dfg.build_visual(args.visual, format="pdf", calls=False, show=False)
