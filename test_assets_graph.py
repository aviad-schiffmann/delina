import unittest
from pathlib import Path

from gcp_asset_graph import build_graph_from_jsonl, effective_roles, all_permissions, get_folder_hierarchy, show_folder_hierarchy
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


RON = "user:ron@test.authomize.com"
DEV_MANAGER = "serviceAccount:dev-manager@striking-arbor-264209.iam.gserviceaccount.com"
EXERCISE_FETCHER = "serviceAccount:exercise-fetcher@striking-arbor-264209.iam.gserviceaccount.com"
REVIEWERS = "group:reviewers@test.authomize.com"


class TestEffectiveRoles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g: DiGraph = build_graph_from_jsonl(DATA_FILE)

    def _roles(self, member: str, resource: str) -> list[str]:
        return effective_roles(self.g, member, resource)

    # ── direct assignments ─────────────────────────────────────────────────

    def test_direct_assignment_on_org(self) -> None:
        self.assertEqual(
            self._roles(RON, "organizations/1066060271767"),
            ["roles/owner", "roles/resourcemanager.folderAdmin"],
        )

    def test_direct_assignment_on_folder(self) -> None:
        self.assertEqual(
            self._roles(DEV_MANAGER, "folders/635215680011"),
            ["roles/owner", "roles/viewer"],
        )

    # ── inherited one level ────────────────────────────────────────────────

    def test_inherited_one_level_from_org(self) -> None:
        roles = self._roles(RON, "folders/767216091627")
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/resourcemanager.folderAdmin", roles)
        self.assertIn("roles/resourcemanager.folderEditor", roles)

    def test_inherited_one_level_from_folder(self) -> None:
        # dev-manager has owner on folders/767216091627 → inherited by folders/188906894377
        roles = self._roles(DEV_MANAGER, "folders/188906894377")
        self.assertIn("roles/owner", roles)

    # ── inherited multiple levels ──────────────────────────────────────────

    def test_inherited_three_levels_deep(self) -> None:
        # org → 767216091627 → 96505015065 → 93198982071
        roles = self._roles(RON, "folders/93198982071")
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/resourcemanager.folderAdmin", roles)
        self.assertIn("roles/resourcemanager.folderEditor", roles)

    def test_inherited_merges_direct_and_ancestor(self) -> None:
        # dev-manager: owner on 635215680011 (direct) + viewer on 767216091627 (ancestor)
        # 518729943705 is child of 635215680011
        roles = self._roles(DEV_MANAGER, "folders/518729943705")
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/viewer", roles)

    # ── no access ─────────────────────────────────────────────────────────

    def test_no_access_returns_empty(self) -> None:
        # reviewers only have viewer on folders/96505015065 subtree, not on 188906894377
        self.assertEqual(self._roles(REVIEWERS, "folders/188906894377"), [])

    def test_unknown_member_returns_empty(self) -> None:
        self.assertEqual(self._roles("user:nobody@test.authomize.com", "folders/188906894377"), [])

    def test_unknown_resource_returns_empty(self) -> None:
        self.assertEqual(self._roles(RON, "folders/000000000000"), [])

    # ── deduplication ─────────────────────────────────────────────────────

    def test_no_duplicate_roles(self) -> None:
        roles = self._roles(RON, "folders/93198982071")
        self.assertEqual(len(roles), len(set(roles)))


class TestAllPermissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g: DiGraph = build_graph_from_jsonl(DATA_FILE)

    def _perms(self, member: str) -> dict[str, list[str]]:
        return all_permissions(self.g, member)

    # ── unknown / no access ───────────────────────────────────────────────

    def test_unknown_member_returns_empty(self) -> None:
        self.assertEqual(self._perms("user:nobody@test.authomize.com"), {})

    # ── ron (org-level owner) ──────────────────────────────────────────────

    def test_ron_can_access_all_resources(self) -> None:
        resources = set(self._perms(RON).keys())
        # ron has owner on the org so every resource below must be reachable
        for expected in [
            "organizations/1066060271767",
            "folders/767216091627", "folders/36290848176", "folders/96505015065",
            "folders/188906894377", "folders/635215680011", "folders/495694787245",
            "folders/518729943705", "folders/837642324986", "folders/93198982071",
            "folders/361332156337", "projects/185023072868", "projects/20671306372",
            "projects/377145543109",
        ]:
            self.assertIn(expected, resources)

    def test_ron_has_owner_on_org(self) -> None:
        self.assertIn("roles/owner", self._perms(RON)["organizations/1066060271767"])

    def test_ron_inherits_owner_on_deep_folder(self) -> None:
        self.assertIn("roles/owner", self._perms(RON)["folders/93198982071"])

    def test_ron_billing_account_direct_only(self) -> None:
        # billing account has no hierarchy edge — direct role only
        self.assertEqual(self._perms(RON)["billingAccounts/01B2E0-10D255-037E4D"], ["roles/billing.admin"])

    # ── dev-manager ────────────────────────────────────────────────────────

    def test_dev_manager_accessible_resources(self) -> None:
        resources = set(self._perms(DEV_MANAGER).keys())
        self.assertIn("folders/635215680011", resources)  # direct
        self.assertIn("folders/518729943705", resources)  # child of 635215680011
        self.assertIn("folders/837642324986", resources)  # child of 635215680011
        # billing account is not reachable via hierarchy
        self.assertNotIn("billingAccounts/01B2E0-10D255-037E4D", resources)

    def test_dev_manager_roles_on_direct_resource(self) -> None:
        roles = self._perms(DEV_MANAGER)["folders/635215680011"]
        self.assertIn("roles/owner", roles)

    def test_dev_manager_inherited_roles_on_child(self) -> None:
        roles = self._perms(DEV_MANAGER)["folders/518729943705"]
        self.assertIn("roles/owner", roles)

    # ── reviewers (scoped to one subtree) ─────────────────────────────────

    def test_reviewers_scoped_to_96505015065_subtree(self) -> None:
        resources = set(self._perms(REVIEWERS).keys())
        self.assertIn("folders/96505015065", resources)
        self.assertIn("folders/93198982071", resources)
        self.assertIn("folders/361332156337", resources)
        # outside the subtree
        self.assertNotIn("folders/767216091627", resources)
        self.assertNotIn("organizations/1066060271767", resources)

    def test_reviewers_role_is_viewer(self) -> None:
        for resource in self._perms(REVIEWERS).values():
            self.assertEqual(resource, ["roles/viewer"])

    # ── deduplication ─────────────────────────────────────────────────────

    def test_no_duplicate_roles_in_any_resource(self) -> None:
        for resource, roles in self._perms(RON).items():
            self.assertEqual(len(roles), len(set(roles)), f"duplicates in {resource}")


if __name__ == "__main__":
    unittest.main()
