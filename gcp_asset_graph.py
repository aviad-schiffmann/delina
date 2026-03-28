"""
Build a directed graph from a GCP Cloud Asset Inventory JSON Lines file.

Edges:
  - Hierarchy: parent -> child (from each asset's `ancestors` list).
  - IAM: member -> resource with `Edge.kind == "iam"` and `Edge.roles`.
"""

from __future__ import annotations

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


def effective_roles(g: DiGraph, member: str, resource: str) -> list[str]:
    """
    Return the deduplicated list of IAM roles *member* has on *resource*,
    including roles inherited from any ancestor resource in the hierarchy.

    Inheritance rule: a role granted on an ancestor resource is implicitly
    granted on all of its descendants (recursively).
    """
    roles: list[str] = []
    seen_roles: set[str] = set()
    visited: set[str] = set()
    queue: list[str] = [resource]

    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)

        # Collect roles granted directly on this resource.
        if g.has_edge(member, current):
            edge = g.edges[member, current]
            if edge.kind == "iam":
                for role in edge.roles:
                    if role not in seen_roles:
                        seen_roles.add(role)
                        roles.append(role)

        # Walk up: hierarchy edges are parent -> child, so predecessors give parents.
        for parent in g.predecessors(current, kind="hierarchy"):
            if parent.id not in visited:
                queue.append(parent.id)

    return roles


def all_permissions(g: DiGraph, member: str) -> dict[str, list[str]]:
    """
    Return every resource the *member* can access and the roles they hold on it,
    including roles inherited from ancestor resources in the hierarchy.

    Returns a dict mapping resource_id -> deduplicated list of roles.
    """
    result: dict[str, list[str]] = {}

    if g._lookup_node(member) is None:
        return result

    for resource_node in g.successors(member, kind="iam"):
        direct_roles = g.edges[member, resource_node.id].roles

        # BFS downward: the member inherits direct_roles on every descendant.
        queue = [resource_node]
        visited: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current.id in visited:
                continue
            visited.add(current.id)

            entry = result.setdefault(current.id, [])
            for role in direct_roles:
                if role not in entry:
                    entry.append(role)

            for child in g.successors(current, kind="hierarchy"):
                queue.append(child)

    return result


def get_folder_hierarchy(g: DiGraph, root: str | None = None) -> dict[str, list[str]]:
    """Return folder hierarchy parent->children via hierarchy edges."""
    hierarchy: dict[str, list[str]] = {}

    for parent_node, child_node, edge in g.edges(data=True):
        if edge.kind != "hierarchy":
            continue

        parent_id = parent_node.id
        child_id = child_node.id

        if not parent_id.startswith(("folders/", "organizations/")):
            continue
        if not child_id.startswith(("folders/", "organizations/")):
            continue

        hierarchy.setdefault(parent_id, []).append(child_id)

    for children in hierarchy.values():
        children.sort()

    if root is None:
        return hierarchy

    if root not in g._nodes:
        return {}

    result: dict[str, list[str]] = {}
    visited: set[str] = set()

    def collect(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)

        result[node_id] = hierarchy.get(node_id, [])
        for child_id in result[node_id]:
            if child_id in hierarchy:
                collect(child_id)

    collect(root)
    return result


def show_folder_hierarchy(g: DiGraph, root: str | None = None) -> str:
    """Return a formatted, indented folder hierarchy string."""
    hierarchy = get_folder_hierarchy(g, root=root)

    if root is not None:
        roots = [root] if root in g._nodes else []
    else:
        children = {c for kids in hierarchy.values() for c in kids}
        roots = sorted([n for n in hierarchy.keys() if n not in children])

    lines: list[str] = []

    def walk(node_id: str, level: int) -> None:
        indent = "  " * level
        lines.append(f"{indent}{node_id}")
        for child_id in hierarchy.get(node_id, []):
            walk(child_id, level + 1)

    visited: set[str] = set()

    def walk(node_id: str, level: int) -> None:
        if node_id in visited:
            return
        visited.add(node_id)

        indent = "  " * level
        lines.append(f"{indent}{node_id}")
        for child_id in hierarchy.get(node_id, []):
            walk(child_id, level + 1)

    for root_id in roots:
        walk(root_id, 0)

    return "\n".join(lines)


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


CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    config = load_config()

    if not DATA_FILE.is_file():
        raise SystemExit(f"Data file not found: {DATA_FILE}")

    g = build_graph_from_jsonl(DATA_FILE)
    if config.get("stats"):
        print(f"Nodes: {g.number_of_nodes()}, Edges: {g.number_of_edges()}")
    if config.get("edges"):
        for _, _, edge in g.edges(data=True):
            print(edge)
    if config.get("folder_hierarchy"):
        root = config.get("folder_hierarchy_root")
        print(show_folder_hierarchy(g, root=root))

    print("2 - Resource hierarchy")
    print("3 - All permissions for a user")
    print("4 - All permissions on a resource")
    print("q - Quit")

    while True:
        choice = input("\nChoice: ").strip()

        if choice == "q":
            break

        elif choice == "2":
            root = input("Root resource (leave blank for full hierarchy): ").strip() or None
            print(show_folder_hierarchy(g, root=root))

        elif choice == "3":
            member = input("Member (e.g. user:ron@test.authomize.com): ").strip()
            perms = all_permissions(g, member)
            if not perms:
                print("No permissions found.")
            else:
                for resource, roles in sorted(perms.items()):
                    asset_type = g._nodes[resource].attrs.get("asset_type", "")
                    for role in roles:
                        print(f'  ("{resource}", "{asset_type}", "{role}")')

        elif choice == "4":
            resource = input("Resource (e.g. folders/123): ").strip()
            found = False
            for node in g._nodes.values():
                if node.attrs.get("node_type") != "member":
                    continue
                roles = effective_roles(g, node.id, resource)
                if roles:
                    print(f"  {node.id}: {roles}")
                    found = True
            if not found:
                print("No permissions found.")

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
