"""
Build a directed graph from a GCP Cloud Asset Inventory JSON Lines file.

Edges:
  - Hierarchy: parent -> child (from each asset's `ancestors` list).
  - IAM: member -> resource with `Edge.kind == "iam"` and `Edge.roles`.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any, Iterator

from graph import DiGraph, Node

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
            g.add_edge(member, resource_key, kind="iam", roles=[role] if role else [])


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
        direct_roles: list[str] = g.edges[member, resource_node.id].roles

        # BFS downward: the member inherits direct_roles on every descendant.
        queue: list[Node] = [resource_node]
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


class PermissionIndex:
    """
    Pre-computed permission index for O(1) query-time lookups.
    a type of cache

    Built once after graph load by running `all_permissions` for every member.
    Trades memory for speed: subsequent `effective_roles` and `all_permissions`
    calls are plain dict lookups instead of graph traversals.
    """

    def __init__(self, g: DiGraph) -> None:
        self._index: dict[str, dict[str, list[str]]] = {
            node.id: all_permissions(g, node.id)
            for node in g._nodes.values()
            if node.node_type == "member"
        }

    def effective_roles(self, member: str, resource: str) -> list[str]:
        return self._index.get(member, {}).get(resource, [])

    def all_permissions(self, member: str) -> dict[str, list[str]]:
        return self._index.get(member, {})


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


def export_html(g: DiGraph, path: Path) -> None:
    """Write an interactive vis.js graph to *path* and open it in the browser."""
    from collections import defaultdict, deque

    LEVEL_SEP = 280   # horizontal distance between resource depth levels
    NODE_SEP  = 160   # vertical distance between nodes at the same level
    MEMBER_Y  = -320  # y position for member row (above the resource tree)

    # ── compute resource depth levels via BFS from hierarchy roots ────────
    children_of: dict[str, list[str]] = defaultdict(list)
    has_parent: set[str] = set()
    for (u, v), edge in g._edges.items():
        if edge.kind == "hierarchy":
            children_of[u.id].append(v.id)
            has_parent.add(v.id)

    resource_ids = [nid for nid, n in g._nodes.items() if n.node_type == "resource"]
    roots = [nid for nid in resource_ids if nid not in has_parent]

    depth: dict[str, int] = {}
    queue: deque[str] = deque()
    for r in roots:
        depth[r] = 0
        queue.append(r)
    while queue:
        nid = queue.popleft()
        for child in children_of[nid]:
            if child not in depth:
                depth[child] = depth[nid] + 1
                queue.append(child)

    # Sort each node's children alphabetically for a stable, readable order.
    for nid in children_of:
        children_of[nid].sort()

    # DFS tree layout: leaves get sequential y slots, parents centre over children.
    node_y: dict[str, float] = {}
    leaf_counter: list[int] = [0]

    def assign_y(nid: str) -> float:
        kids = children_of.get(nid, [])
        if not kids:
            y = leaf_counter[0] * NODE_SEP
            leaf_counter[0] += 1
        else:
            child_ys = [assign_y(c) for c in kids]
            y = (child_ys[0] + child_ys[-1]) / 2
        node_y[nid] = y
        return y

    for r in sorted(roots):
        assign_y(r)

    # Any resource not reachable from a root gets its own slot at the bottom.
    for nid in resource_ids:
        if nid not in node_y:
            node_y[nid] = leaf_counter[0] * NODE_SEP
            leaf_counter[0] += 1

    positions: dict[str, tuple[int, int]] = {
        nid: (depth.get(nid, 0) * LEVEL_SEP, int(node_y[nid]))
        for nid in resource_ids
    }

    # ── spread members evenly across the top ──────────────────────────────
    member_ids = [nid for nid, n in g._nodes.items() if n.node_type == "member"]
    total_width = max(depth.values(), default=0) * LEVEL_SEP
    member_sep = max(LEVEL_SEP, total_width // max(len(member_ids), 1))
    for idx, nid in enumerate(member_ids):
        positions[nid] = (idx * member_sep + 160*6, MEMBER_Y)

    # ── SVG bounds ────────────────────────────────────────────────────────
    NW, NH = 160, 36
    PAD    = 80
    all_x  = [x for x, _ in positions.values()]
    all_y  = [y for _, y in positions.values()]
    vx0 = min(all_x) - NW // 2 - PAD
    vy0 = min(all_y) - NH // 2 - PAD
    vw0 = max(all_x) - min(all_x) + NW + PAD * 2
    vh0 = max(all_y) - min(all_y) + NH + PAD * 2

    # ── SVG elements ──────────────────────────────────────────────────────
    elems: list[str] = []

    # edges first (under nodes)
    for (u, v), edge in g._edges.items():
        ux, uy = positions.get(u.id, (0, 0))
        ex, ey = positions.get(v.id, (0, 0))
        if edge.kind == "hierarchy":
            # parent right-center → mid-x turn → child y → child left-center
            x1, y1 = ux + NW // 2, uy
            x2, y2 = ex - NW // 2, ey
            mx = (x1 + x2) // 2
            d = f"M{x1},{y1} H{mx} V{y2} H{x2}"
            elems.append(f'<path d="{d}" class="eh" marker-end="url(#ah)"><title>hierarchy</title></path>')
        else:
            # member bottom-center → resource y → resource left-center
            x1, y1 = ux, uy + NH // 2
            x2, y2 = ex - NW // 2, ey
            tip = "\n".join(edge.roles)
            d = f"M{x1},{y1} V{y2} H{x2}"
            elems.append(f'<path d="{d}" class="ei" marker-end="url(#ai)"><title>{tip}</title></path>')

    # nodes on top
    for nid, node in g._nodes.items():
        nx, ny = positions.get(nid, (0, 0))
        label = nid.split("/")[-1]
        if len(label) > 20:
            label = label[:18] + "…"
        if node.node_type == "member":
            elems.append(
                f'<g class="nm"><title>{nid}</title>'
                f'<ellipse cx="{nx}" cy="{ny}" rx="{NW//2}" ry="{NH//2}"/>'
                f'<text x="{nx}" y="{ny}">{label}</text></g>'
            )
        else:
            elems.append(
                f'<g class="nr"><title>{nid}</title>'
                f'<rect x="{nx - NW//2}" y="{ny - NH//2}" width="{NW}" height="{NH}" rx="4"/>'
                f'<text x="{nx}" y="{ny}">{label}</text></g>'
            )

    body = "\n  ".join(elems)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>GCP Asset Graph</title>
  <style>
    body {{ margin:0; overflow:hidden; background:#f5f6fa; font-family:sans-serif; }}
    svg {{ width:100vw; height:100vh; cursor:grab; }}
    svg:active {{ cursor:grabbing; }}
    .nr rect    {{ fill:#7EB6D9; stroke:#4a90c4; stroke-width:1.5; }}
    .nm ellipse {{ fill:#7EC8A4; stroke:#3a9a6a; stroke-width:1.5; }}
    text {{ font-size:11px; fill:#111; pointer-events:none;
            text-anchor:middle; dominant-baseline:middle; }}
    .eh {{ stroke:#aaa; stroke-width:1.5; fill:none; }}
    .ei {{ stroke:#E8855A; stroke-width:1.5; fill:none; stroke-dasharray:6,3; }}
    #legend {{ position:fixed; top:12px; left:12px; background:rgba(255,255,255,.92);
               padding:10px 14px; border-radius:6px; font-size:13px; line-height:1.9; }}
  </style>
</head>
<body>
<svg id="S" viewBox="{vx0} {vy0} {vw0} {vh0}">
  <defs>
    <marker id="ah" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
      <polygon points="0 0,8 3,0 6" fill="#aaa"/>
    </marker>
    <marker id="ai" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
      <polygon points="0 0,8 3,0 6" fill="#E8855A"/>
    </marker>
  </defs>
  {body}
</svg>
<div id="legend">
  <b>Nodes</b><br>
  <span style="color:#7EB6D9">■</span> Resource &nbsp;
  <span style="color:#7EC8A4">●</span> Member<br>
  <b>Edges</b><br>
  <span style="color:#aaa">—</span> Hierarchy &nbsp;
  <span style="color:#E8855A">- -</span> IAM (hover for roles)
</div>
<script>
  const S = document.getElementById('S');
  let [vx,vy,vw,vh] = [{vx0},{vy0},{vw0},{vh0}];
  const setVB = () => S.setAttribute('viewBox',`${{vx}} ${{vy}} ${{vw}} ${{vh}}`);
  let drag=false, ox=0, oy=0;
  S.addEventListener('mousedown', e => {{ drag=true; ox=e.clientX; oy=e.clientY; }});
  window.addEventListener('mousemove', e => {{
    if(!drag) return;
    vx -= (e.clientX-ox)/S.clientWidth*vw;
    vy -= (e.clientY-oy)/S.clientHeight*vh;
    ox=e.clientX; oy=e.clientY; setVB();
  }});
  window.addEventListener('mouseup', () => drag=false);
  S.addEventListener('wheel', e => {{
    e.preventDefault();
    const f = e.deltaY>0 ? 1.1 : 0.9;
    const mx = e.offsetX/S.clientWidth*vw+vx;
    const my = e.offsetY/S.clientHeight*vh+vy;
    vx=mx-(mx-vx)*f; vy=my-(my-vy)*f; vw*=f; vh*=f; setVB();
  }}, {{passive:false}});
</script>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")


CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.is_file():
        return {}
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    config = load_config()

    if not DATA_FILE.is_file():
        raise SystemExit(f"Data file not found: {DATA_FILE}")

    g = build_graph_from_jsonl(DATA_FILE)
    index = PermissionIndex(g)
    if config.get("stats"):
        print(f"Nodes: {g.number_of_nodes()}, Edges: {g.number_of_edges()}")
    if config.get("edges"):
        for _, _, edge in g.edges(data=True):
            print(edge)
    if config.get("folder_hierarchy"):
        root = config.get("folder_hierarchy_root")
        print(show_folder_hierarchy(g, root=root))

    print("1 - Full graph")
    print("2 - Resource hierarchy")
    print("3 - All permissions for a user")
    print("4 - All permissions on a resource")
    print("q - Quit")

    while True:
        choice = input("\nChoice: ").strip()

        if choice == "q":
            break

        elif choice == "1":
            out = Path(__file__).resolve().parent / "graph.html"
            export_html(g, out)
            webbrowser.open(out.as_uri())
            print(f"Opened {out}")

        elif choice == "2":
            root = input("Root resource (leave blank for full hierarchy): ").strip() or None
            print(show_folder_hierarchy(g, root=root))

        elif choice == "3":
            member = input("Member (e.g. user:ron@test.authomize.com): ").strip()
            perms = index.all_permissions(member)
            if not perms:
                print("No permissions found.")
            else:
                for resource, roles in sorted(perms.items()):
                    asset_type = g._nodes[resource].asset_type
                    for role in roles:
                        print(f'  ("{resource}", "{asset_type}", "{role}")')

        elif choice == "4":
            resource = input("Resource (e.g. folders/123): ").strip()
            found = False
            for node in g._nodes.values():
                if node.node_type != "member":
                    continue
                roles = index.effective_roles(node.id, resource)
                if roles:
                    print(f"  {node.id}: {roles}")
                    found = True
            if not found:
                print("No permissions found.")

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
