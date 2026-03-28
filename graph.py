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
    attrs: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Node) and self.id == other.id


@dataclass(slots=True)
class Edge:
    """Directed edge: tail ``from_node`` -> head ``to_node``, plus kind/roles for GCP IAM vs hierarchy."""

    from_node: Node
    to_node: Node
    kind: str = ""
    roles: list[str] = field(default_factory=list)

    def merge(self, *, kind: str | None = None, roles: list[str] | None = None, **_: Any) -> None:
        if kind is not None:
            self.kind = kind
        if roles is not None:
            for r in roles:
                if r and r not in self.roles:
                    self.roles.append(r)

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
            if isinstance(x, Node):
                self._nodes[nid] = Node(nid, dict(x.attrs))
            else:
                self._nodes[nid] = Node(nid)
        elif isinstance(x, Node) and x.attrs:
            self._nodes[nid].attrs.update(x.attrs)
        return self._nodes[nid]

    def add_node(self, node: str | Node, **attr: Any) -> None:
        n = self._ensure_node(node)
        n.attrs.update(attr)

    def add_edge(self, u: str | Node, v: str | Node, **attr: Any) -> None:
        u_n = self._ensure_node(u)
        v_n = self._ensure_node(v)
        key = (u_n, v_n)
        if key not in self._edges:
            self._edges[key] = Edge(from_node=u_n, to_node=v_n)
        self._edges[key].merge(**attr)

    def has_edge(self, u: str | Node, v: str | Node) -> bool:
        u_n = self._lookup_node(u)
        v_n = self._lookup_node(v)
        if u_n is None or v_n is None:
            return False
        return (u_n, v_n) in self._edges
