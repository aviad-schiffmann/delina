"""
Directed graph with first-class Node and Edge objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(slots=True)
class Node:
    """Graph vertex, keyed by `id` (e.g. GCP resource key or IAM member string)."""

    id: str
    node_type: str = ""
    asset_type: str = ""

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Node) and self.id == other.id


@dataclass
class Edge:
    """Directed edge: tail ``from_node`` -> head ``to_node``, plus kind/roles for GCP IAM vs hierarchy."""

    from_node: Node
    to_node: Node
    kind: str = ""
    _roles: set[str] = field(default_factory=set)

    @property
    def roles(self) -> list[str]:
        return sorted(self._roles)

    def merge(self, *, kind: str | None = None, roles: list[str] | None = None, **_: Any) -> None:
        if kind is not None:
            self.kind = kind
        if roles is not None:
            self._roles.update(r for r in roles if r)

    def __repr__(self) -> str:
        return f"Edge({self.from_node.id!r} -> {self.to_node.id!r}, kind={self.kind!r}, roles={self.roles!r})"


class _EdgeView:
    __slots__ = ("_g",)

    def __init__(self, g: DiGraph) -> None:
        self._g = g

    def __call__(self, data: bool = False) -> Iterator[Any]:
        if data:
            for (u, v), e in self._g._edges.items():
                yield u, v, e
        else:
            for u, v in self._g._edges:
                yield u, v

    def __getitem__(self, key: tuple[Any, Any]) -> Edge:
        u, v = key
        u_n = self._g._lookup_node(u)
        v_n = self._g._lookup_node(v)
        if u_n is None or v_n is None:
            raise KeyError(key)
        ek = (u_n, v_n)
        if ek not in self._g._edges:
            raise KeyError(key)
        return self._g._edges[ek]


class DiGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[Node, Node], Edge] = {}
        self._adj: dict[Node, list[Node]] = {}   # out-neighbors
        self._radj: dict[Node, list[Node]] = {}  # in-neighbors

    @property
    def edges(self) -> _EdgeView:
        return _EdgeView(self)

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return len(self._edges)

    def _lookup_node(self, x: str | Node) -> Node | None:
        nid = x.id if isinstance(x, Node) else x
        return self._nodes.get(nid)

    def _ensure_node(self, x: str | Node) -> Node:
        nid = x.id if isinstance(x, Node) else x
        if nid not in self._nodes:
            self._nodes[nid] = Node(nid) if not isinstance(x, Node) else Node(nid, x.node_type, x.asset_type)
            n = self._nodes[nid]
            self._adj[n] = []
            self._radj[n] = []
        elif isinstance(x, Node):
            n = self._nodes[nid]
            if x.node_type:
                n.node_type = x.node_type
            if x.asset_type:
                n.asset_type = x.asset_type
        return self._nodes[nid]

    def add_node(self, node: str | Node, **attr: Any) -> None:
        n = self._ensure_node(node)
        if "node_type" in attr:
            n.node_type = attr["node_type"]
        if "asset_type" in attr:
            n.asset_type = attr["asset_type"]

    def add_edge(self, u: str | Node, v: str | Node, **attr: Any) -> None:
        u_n = self._ensure_node(u)
        v_n = self._ensure_node(v)
        key = (u_n, v_n)
        if key not in self._edges:
            self._edges[key] = Edge(from_node=u_n, to_node=v_n)
            self._adj[u_n].append(v_n)
            self._radj[v_n].append(u_n)
        self._edges[key].merge(**attr)

    def has_edge(self, u: str | Node, v: str | Node) -> bool:
        u_n = self._lookup_node(u)
        v_n = self._lookup_node(v)
        if u_n is None or v_n is None:
            return False
        return (u_n, v_n) in self._edges

    def successors(self, node: str | Node, kind: str | None = None) -> Iterator[Node]:
        """Yield nodes reachable from *node* via one outgoing edge (optionally filtered by kind)."""
        n = self._lookup_node(node)
        if n is None:
            return
        for v in self._adj[n]:
            if kind is None or self._edges[(n, v)].kind == kind:
                yield v

    def predecessors(self, node: str | Node, kind: str | None = None) -> Iterator[Node]:
        """Yield nodes that have an outgoing edge to *node* (optionally filtered by kind)."""
        n = self._lookup_node(node)
        if n is None:
            return
        for u in self._radj[n]:
            if kind is None or self._edges[(u, n)].kind == kind:
                yield u

    def ancestors(self, node: str | Node, kind: str | None = None) -> list[Node]:
        """
        Return all ancestors of *node* reachable by walking incoming edges, in
        breadth-first order (closest ancestors first).

        *kind* filters which edges are followed (e.g. ``"hierarchy"``).
        The start node itself is not included.
        """
        start = self._lookup_node(node)
        if start is None:
            return []
        visited: set[Node] = {start}
        queue: list[Node] = [start]
        result: list[Node] = []
        while queue:
            current = queue.pop(0)
            for parent in self.predecessors(current, kind=kind):
                if parent not in visited:
                    visited.add(parent)
                    result.append(parent)
                    queue.append(parent)
        return result
