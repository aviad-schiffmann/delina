"""Unit tests for graph.py — Node, Edge, and DiGraph."""

import unittest

from graph import DiGraph, Edge, Node


class TestNode(unittest.TestCase):
    def test_equality_by_id(self) -> None:
        self.assertEqual(Node("a"), Node("a"))
        self.assertNotEqual(Node("a"), Node("b"))

    def test_hash_by_id(self) -> None:
        self.assertEqual(hash(Node("x")), hash(Node("x")))
        s = {Node("x"), Node("x"), Node("y")}
        self.assertEqual(len(s), 2)

    def test_equality_ignores_type_fields(self) -> None:
        self.assertEqual(Node("a", node_type="folder"), Node("a", node_type="project"))

    def test_not_equal_to_non_node(self) -> None:
        self.assertNotEqual(Node("a"), "a")


class TestEdge(unittest.TestCase):
    def _make_edge(self) -> Edge:
        return Edge(from_node=Node("u"), to_node=Node("v"))

    def test_roles_sorted(self) -> None:
        e = self._make_edge()
        e.merge(roles=["roles/viewer", "roles/owner"])
        self.assertEqual(e.roles, ["roles/owner", "roles/viewer"])

    def test_merge_kind(self) -> None:
        e = self._make_edge()
        e.merge(kind="hierarchy")
        self.assertEqual(e.kind, "hierarchy")

    def test_merge_roles_dedup(self) -> None:
        e = self._make_edge()
        e.merge(roles=["roles/owner"])
        e.merge(roles=["roles/owner", "roles/viewer"])
        self.assertEqual(e.roles, ["roles/owner", "roles/viewer"])

    def test_merge_empty_roles_ignored(self) -> None:
        e = self._make_edge()
        e.merge(roles=["", "roles/viewer"])
        self.assertEqual(e.roles, ["roles/viewer"])

    def test_repr(self) -> None:
        e = self._make_edge()
        r = repr(e)
        self.assertIn("u", r)
        self.assertIn("v", r)


class TestDiGraphNodes(unittest.TestCase):
    def setUp(self) -> None:
        self.g = DiGraph()

    def test_add_node_str(self) -> None:
        self.g.add_node("a")
        self.assertEqual(self.g.number_of_nodes(), 1)

    def test_add_node_node_object(self) -> None:
        self.g.add_node(Node("b", node_type="folder"))
        self.assertEqual(self.g.number_of_nodes(), 1)
        n = self.g._nodes["b"]
        self.assertEqual(n.node_type, "folder")

    def test_add_node_kwargs(self) -> None:
        self.g.add_node("c", node_type="project", asset_type="cloudresourcemanager.Project")
        n = self.g._nodes["c"]
        self.assertEqual(n.node_type, "project")
        self.assertEqual(n.asset_type, "cloudresourcemanager.Project")

    def test_add_node_upserts_attrs(self) -> None:
        self.g.add_node("d")
        self.g.add_node("d", node_type="org")
        self.assertEqual(self.g._nodes["d"].node_type, "org")
        self.assertEqual(self.g.number_of_nodes(), 1)

    def test_add_duplicate_node_does_not_double_count(self) -> None:
        self.g.add_node("e")
        self.g.add_node("e")
        self.assertEqual(self.g.number_of_nodes(), 1)


class TestDiGraphEdges(unittest.TestCase):
    def setUp(self) -> None:
        self.g = DiGraph()

    def test_add_edge_creates_nodes(self) -> None:
        self.g.add_edge("a", "b")
        self.assertEqual(self.g.number_of_nodes(), 2)
        self.assertEqual(self.g.number_of_edges(), 1)

    def test_has_edge_true(self) -> None:
        self.g.add_edge("a", "b")
        self.assertTrue(self.g.has_edge("a", "b"))

    def test_has_edge_false_reversed(self) -> None:
        self.g.add_edge("a", "b")
        self.assertFalse(self.g.has_edge("b", "a"))

    def test_has_edge_unknown_nodes(self) -> None:
        self.assertFalse(self.g.has_edge("x", "y"))

    def test_add_edge_with_node_objects(self) -> None:
        self.g.add_edge(Node("u"), Node("v"))
        self.assertTrue(self.g.has_edge("u", "v"))

    def test_add_duplicate_edge_merges(self) -> None:
        self.g.add_edge("a", "b", kind="iam", roles=["roles/owner"])
        self.g.add_edge("a", "b", roles=["roles/viewer"])
        self.assertEqual(self.g.number_of_edges(), 1)
        e = self.g.edges[("a", "b")]
        self.assertIn("roles/owner", e.roles)
        self.assertIn("roles/viewer", e.roles)

    def test_edges_view_no_data(self) -> None:
        self.g.add_edge("a", "b")
        self.g.add_edge("b", "c")
        pairs = list(self.g.edges())
        self.assertEqual(len(pairs), 2)
        u, v = pairs[0]
        self.assertIsInstance(u, Node)
        self.assertIsInstance(v, Node)

    def test_edges_view_with_data(self) -> None:
        self.g.add_edge("a", "b", kind="hierarchy")
        triples = list(self.g.edges(data=True))
        self.assertEqual(len(triples), 1)
        _, _, e = triples[0]
        self.assertIsInstance(e, Edge)
        self.assertEqual(e.kind, "hierarchy")

    def test_edges_view_getitem(self) -> None:
        self.g.add_edge("a", "b", kind="iam")
        e = self.g.edges[("a", "b")]
        self.assertEqual(e.kind, "iam")

    def test_edges_view_getitem_missing_raises(self) -> None:
        self.g.add_edge("a", "b")
        with self.assertRaises(KeyError):
            _ = self.g.edges[("b", "a")]

    def test_edges_view_getitem_unknown_node_raises(self) -> None:
        with self.assertRaises(KeyError):
            _ = self.g.edges[("x", "y")]


class TestDiGraphTraversal(unittest.TestCase):
    def setUp(self) -> None:
        #   org
        #   ├── folder_a
        #   │   └── folder_b
        #   └── folder_c
        # iam edge: member -> folder_a
        self.g = DiGraph()
        self.g.add_edge("org", "folder_a", kind="hierarchy")
        self.g.add_edge("folder_a", "folder_b", kind="hierarchy")
        self.g.add_edge("org", "folder_c", kind="hierarchy")
        self.g.add_edge("member", "folder_a", kind="iam")

    def _ids(self, nodes) -> list[str]:
        return [n.id for n in nodes]

    # successors
    def test_successors_all(self) -> None:
        self.assertCountEqual(self._ids(self.g.successors("org")), ["folder_a", "folder_c"])

    def test_successors_kind_filter(self) -> None:
        self.assertEqual(self._ids(self.g.successors("org", kind="hierarchy")), ["folder_a", "folder_c"])
        self.assertEqual(self._ids(self.g.successors("member", kind="hierarchy")), [])
        self.assertEqual(self._ids(self.g.successors("member", kind="iam")), ["folder_a"])

    def test_successors_unknown_node(self) -> None:
        self.assertEqual(self._ids(self.g.successors("ghost")), [])

    # predecessors
    def test_predecessors_all(self) -> None:
        self.assertCountEqual(self._ids(self.g.predecessors("folder_a")), ["org", "member"])

    def test_predecessors_kind_filter(self) -> None:
        self.assertEqual(self._ids(self.g.predecessors("folder_a", kind="hierarchy")), ["org"])
        self.assertEqual(self._ids(self.g.predecessors("folder_a", kind="iam")), ["member"])

    def test_predecessors_unknown_node(self) -> None:
        self.assertEqual(self._ids(self.g.predecessors("ghost")), [])

    # ancestors
    def test_ancestors_bfs_order(self) -> None:
        # folder_b's closest ancestor is folder_a, then org
        ids = self._ids(self.g.ancestors("folder_b", kind="hierarchy"))
        self.assertEqual(ids, ["folder_a", "org"])

    def test_ancestors_kind_filter_excludes_iam(self) -> None:
        # member -> folder_a is iam, so ancestors of folder_a via hierarchy = [org]
        self.assertEqual(self._ids(self.g.ancestors("folder_a", kind="hierarchy")), ["org"])

    def test_ancestors_no_kind_filter_includes_all(self) -> None:
        ancestors = self._ids(self.g.ancestors("folder_a"))
        self.assertIn("org", ancestors)
        self.assertIn("member", ancestors)

    def test_ancestors_root_node_returns_empty(self) -> None:
        self.assertEqual(self.g.ancestors("org", kind="hierarchy"), [])

    def test_ancestors_unknown_node_returns_empty(self) -> None:
        self.assertEqual(self.g.ancestors("ghost"), [])

    def test_ancestors_start_node_not_included(self) -> None:
        ancestors = self.g.ancestors("folder_b")
        ids = self._ids(ancestors)
        self.assertNotIn("folder_b", ids)

    def test_ancestors_no_duplicates(self) -> None:
        # diamond: org -> a, org -> b, a -> c, b -> c
        g = DiGraph()
        g.add_edge("org", "a", kind="h")
        g.add_edge("org", "b", kind="h")
        g.add_edge("a", "c", kind="h")
        g.add_edge("b", "c", kind="h")
        ids = [n.id for n in g.ancestors("c", kind="h")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("org", ids)


if __name__ == "__main__":
    unittest.main()
