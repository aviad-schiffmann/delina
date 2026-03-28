import unittest
from pathlib import Path

from gcp_asset_graph import build_graph_from_jsonl, get_folder_hierarchy, show_folder_hierarchy
from graph import DiGraph

DATA_FILE = Path(__file__).resolve().parent / "sample_assets.jsonl"


class TestAncestors(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g: DiGraph = build_graph_from_jsonl(DATA_FILE)

    def _ancestor_ids(self, resource: str) -> list[str]:
        return [n.id for n in self.g.ancestors(resource, kind="hierarchy")]

    # ── root / detached ────────────────────────────────────────────────────

    def test_organization_has_no_ancestors(self) -> None:
        self.assertEqual(self._ancestor_ids("organizations/1066060271767"), [])

    def test_billing_account_has_no_hierarchy_edges(self) -> None:
        # Billing accounts appear in the org but have no hierarchy edge in the graph.
        self.assertEqual(self._ancestor_ids("billingAccounts/01B2E0-10D255-037E4D"), [])

    def test_storage_bucket_has_no_hierarchy_edges(self) -> None:
        # Bucket ancestors list starts at the project, not the bucket itself —
        # so no edge is created from project to bucket.
        self.assertEqual(self._ancestor_ids("storage.googleapis.com/authomize-exercise-data"), [])

    # ── one level below org ────────────────────────────────────────────────

    def test_folder_767216091627_parent_is_org(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/767216091627"),
            ["organizations/1066060271767"],
        )

    def test_folder_36290848176_parent_is_org(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/36290848176"),
            ["organizations/1066060271767"],
        )

    def test_folder_96505015065_parent_is_org(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/96505015065"),
            ["folders/767216091627", "organizations/1066060271767"],
        )

    def test_project_185023072868_parent_is_org(self) -> None:
        self.assertEqual(
            self._ancestor_ids("projects/185023072868"),
            ["organizations/1066060271767"],
        )

    def test_project_377145543109_parent_is_org(self) -> None:
        self.assertEqual(
            self._ancestor_ids("projects/377145543109"),
            ["organizations/1066060271767"],
        )

    # ── two levels deep ────────────────────────────────────────────────────

    def test_folder_188906894377_two_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/188906894377"),
            ["folders/767216091627", "organizations/1066060271767"],
        )

    def test_folder_635215680011_two_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/635215680011"),
            ["folders/767216091627", "organizations/1066060271767"],
        )

    def test_folder_495694787245_two_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/495694787245"),
            ["folders/36290848176", "organizations/1066060271767"],
        )

    def test_project_20671306372_two_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("projects/20671306372"),
            ["folders/36290848176", "organizations/1066060271767"],
        )

    # ── three levels deep ─────────────────────────────────────────────────

    def test_folder_518729943705_three_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/518729943705"),
            ["folders/635215680011", "folders/767216091627", "organizations/1066060271767"],
        )

    def test_folder_837642324986_three_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/837642324986"),
            ["folders/635215680011", "folders/767216091627", "organizations/1066060271767"],
        )

    def test_folder_93198982071_three_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/93198982071"),
            ["folders/96505015065", "folders/767216091627", "organizations/1066060271767"],
        )

    def test_folder_361332156337_three_levels(self) -> None:
        self.assertEqual(
            self._ancestor_ids("folders/361332156337"),
            ["folders/96505015065", "folders/767216091627", "organizations/1066060271767"],
        )

    def test_get_folder_hierarchy_root_org(self) -> None:
        h = get_folder_hierarchy(self.g, root="organizations/1066060271767")
        self.assertEqual(
            h.get("organizations/1066060271767"),
            ["folders/36290848176", "folders/767216091627", "folders/96505015065"],
        )
        self.assertEqual(h.get("folders/96505015065"), ["folders/361332156337", "folders/93198982071"])

    def test_show_folder_hierarchy_output(self) -> None:
        output = show_folder_hierarchy(self.g, root="organizations/1066060271767")
        self.assertIn("organizations/1066060271767", output)
        self.assertIn("  folders/36290848176", output)
        self.assertIn("    folders/495694787245", output)
        self.assertEqual(output.count("folders/96505015065"), 1)


if __name__ == "__main__":
    unittest.main()
