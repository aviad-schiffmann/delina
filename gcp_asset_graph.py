"""
Build a directed graph from a GCP Cloud Asset Inventory JSON Lines file.

Edges:
  - Hierarchy: parent -> child (from each asset's `ancestors` list).
  - IAM: member -> resource with `Edge.kind == "iam"` and `Edge.roles`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

from graph import DiGraph

# GCP asset inventory JSON Lines (one JSON object per line), next to this script.
DATA_FILE = Path(__file__).resolve().parent / "sample_assets.jsonl"


def resource_key_from_name(name: str) -> str:
    """
    Normalize `name` (full resource URL) to a short id consistent with
    `ancestors` entries, e.g. folders/123, organizations/456, billingAccounts/...
    """
    rest = name.split("//", 1)[-1]
    parts = [p for p in rest.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return "/".join(parts)


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_no}: {e}") from e


def add_hierarchy_edges(g: DiGraph, ancestors: list[str]) -> None:
    """
    GCP order: ancestors[0] is the resource, ancestors[1] is its parent, etc.
    Add edges parent -> child: ancestors[i+1] -> ancestors[i].
    """
    for i in range(len(ancestors) - 1):
        child, parent = ancestors[i], ancestors[i + 1]
        g.add_edge(parent, child, kind="hierarchy")


def add_iam_edges(g: DiGraph, resource_key: str, iam_policy: dict[str, Any]) -> None:
    bindings = iam_policy.get("bindings") or []
    for binding in bindings:
        role = binding.get("role") or ""
        for member in binding.get("members") or []:
            g.add_node(member, node_type="member")
            if g.has_edge(member, resource_key):
                edge = g.edges[member, resource_key]
                if edge.kind != "iam":
                    continue
                if role and role not in edge.roles:
                    edge.roles.append(role)
            else:
                g.add_edge(
                    member,
                    resource_key,
                    kind="iam",
                    roles=[role] if role else [],
                )


def build_graph_from_jsonl(path: Path) -> DiGraph:
    g = DiGraph()
    for asset in iter_jsonl(path):
        name = asset.get("name") or ""
        if not name:
            continue
        resource_key = resource_key_from_name(name)
        g.add_node(resource_key, asset_type=asset.get("asset_type"), node_type="resource")

        ancestors = asset.get("ancestors") or []
        if ancestors:
            add_hierarchy_edges(g, ancestors)

        iam = asset.get("iam_policy")
        if isinstance(iam, dict):
            add_iam_edges(g, resource_key, iam)

    return g


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a DiGraph from GCP asset JSONL.")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print node and edge counts.",
    )
    parser.add_argument(
        "--edges",
        action="store_true",
        help="Print all edges with attributes.",
    )
    args = parser.parse_args()

    if not DATA_FILE.is_file():
        raise SystemExit(f"Data file not found: {DATA_FILE}")

    g = build_graph_from_jsonl(DATA_FILE)
    if args.stats:
        print(f"Nodes: {g.number_of_nodes()}, Edges: {g.number_of_edges()}")
    if args.edges:
        for _, _, edge in g.edges(data=True):
            print(edge)


if __name__ == "__main__":
    main()
