import unittest
from pathlib import Path

from gcp_asset_graph import build_graph_from_jsonl, effective_roles, all_permissions, get_folder_hierarchy, show_folder_hierarchy
from graph import DiGraph

DATA_FILE = Path(__file__).resolve().parent / "sample_assets.jsonl"

# Path-based node keys for every hierarchy resource.
ORG         = "organizations/1066060271767"
F767        = "organizations/1066060271767/folders/767216091627"
F36         = "organizations/1066060271767/folders/36290848176"
# folders/96505015065 exists at two distinct positions in the hierarchy.
F96_DIRECT  = "organizations/1066060271767/folders/96505015065"                   # direct child of org
F96_UNDER767 = "organizations/1066060271767/folders/767216091627/folders/96505015065"  # child of 767216091627
F188        = "organizations/1066060271767/folders/767216091627/folders/188906894377"
F635        = "organizations/1066060271767/folders/767216091627/folders/635215680011"
F495        = "organizations/1066060271767/folders/36290848176/folders/495694787245"
F518        = "organizations/1066060271767/folders/767216091627/folders/635215680011/folders/518729943705"
F837        = "organizations/1066060271767/folders/767216091627/folders/635215680011/folders/837642324986"
F93         = "organizations/1066060271767/folders/767216091627/folders/96505015065/folders/93198982071"
F361        = "organizations/1066060271767/folders/767216091627/folders/96505015065/folders/361332156337"
P185        = "organizations/1066060271767/projects/185023072868"
P20         = "organizations/1066060271767/folders/36290848176/projects/20671306372"
P377        = "organizations/1066060271767/projects/377145543109"
BILLING     = "billingAccounts/01B2E0-10D255-037E4D"
BUCKET      = "storage.googleapis.com/authomize-exercise-data"


class TestAncestors(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g: DiGraph = build_graph_from_jsonl(DATA_FILE)

    def _ancestor_ids(self, resource: str) -> list[str]:
        return [n.id for n in self.g.ancestors(resource, kind="hierarchy")]

    # ── root / detached ────────────────────────────────────────────────────

    def test_organization_has_no_ancestors(self) -> None:
        self.assertEqual(self._ancestor_ids(ORG), [])

    def test_billing_account_has_no_hierarchy_edges(self) -> None:
        self.assertEqual(self._ancestor_ids(BILLING), [])

    def test_storage_bucket_has_no_hierarchy_edges(self) -> None:
        self.assertEqual(self._ancestor_ids(BUCKET), [])

    # ── one level below org ────────────────────────────────────────────────

    def test_folder_767216091627_parent_is_org(self) -> None:
        self.assertEqual(self._ancestor_ids(F767), [ORG])

    def test_folder_36290848176_parent_is_org(self) -> None:
        self.assertEqual(self._ancestor_ids(F36), [ORG])

    def test_folder_96505015065_direct_parent_is_org(self) -> None:
        self.assertEqual(self._ancestor_ids(F96_DIRECT), [ORG])

    def test_project_185023072868_parent_is_org(self) -> None:
        self.assertEqual(self._ancestor_ids(P185), [ORG])

    def test_project_377145543109_parent_is_org(self) -> None:
        self.assertEqual(self._ancestor_ids(P377), [ORG])

    # ── two levels deep ────────────────────────────────────────────────────

    def test_folder_188906894377_two_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F188), [F767, ORG])

    def test_folder_635215680011_two_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F635), [F767, ORG])

    def test_folder_495694787245_two_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F495), [F36, ORG])

    def test_project_20671306372_two_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(P20), [F36, ORG])

    # ── three levels deep ─────────────────────────────────────────────────

    def test_folder_518729943705_three_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F518), [F635, F767, ORG])

    def test_folder_837642324986_three_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F837), [F635, F767, ORG])

    def test_folder_93198982071_three_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F93), [F96_UNDER767, F767, ORG])

    def test_folder_361332156337_three_levels(self) -> None:
        self.assertEqual(self._ancestor_ids(F361), [F96_UNDER767, F767, ORG])

    def test_get_folder_hierarchy_root_org(self) -> None:
        h = get_folder_hierarchy(self.g, root=ORG)
        self.assertEqual(
            h.get(ORG),
            [F36, F767, F96_DIRECT],
        )
        self.assertEqual(
            h.get(F96_UNDER767),
            [F361, F93],
        )

    def test_show_folder_hierarchy_output(self) -> None:
        output = show_folder_hierarchy(self.g, root=ORG)
        self.assertIn("organizations/1066060271767", output)
        self.assertIn("  folders/36290848176", output)
        self.assertIn("    folders/495694787245", output)
        # folders/96505015065 appears twice: once as direct child of org,
        # once as child of folders/767216091627.
        self.assertEqual(output.count("folders/96505015065"), 2)


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
            self._roles(RON, ORG),
            ["roles/owner", "roles/resourcemanager.folderAdmin"],
        )

    def test_direct_assignment_on_folder(self) -> None:
        self.assertEqual(
            self._roles(DEV_MANAGER, F635),
            ["roles/owner", "roles/viewer"],
        )

    # ── inherited one level ────────────────────────────────────────────────

    def test_inherited_one_level_from_org(self) -> None:
        roles = self._roles(RON, F767)
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/resourcemanager.folderAdmin", roles)
        self.assertIn("roles/resourcemanager.folderEditor", roles)

    def test_inherited_one_level_from_folder(self) -> None:
        # dev-manager has owner on F767 → inherited by F188
        roles = self._roles(DEV_MANAGER, F188)
        self.assertIn("roles/owner", roles)

    # ── inherited multiple levels ──────────────────────────────────────────

    def test_inherited_three_levels_deep(self) -> None:
        # org → F767 → F96_UNDER767 → F93
        roles = self._roles(RON, F93)
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/resourcemanager.folderAdmin", roles)
        self.assertIn("roles/resourcemanager.folderEditor", roles)

    def test_inherited_merges_direct_and_ancestor(self) -> None:
        # dev-manager: owner on F635 (direct) + viewer on F767 (ancestor)
        # F518 is child of F635
        roles = self._roles(DEV_MANAGER, F518)
        self.assertIn("roles/owner", roles)
        self.assertIn("roles/viewer", roles)

    # ── no access ─────────────────────────────────────────────────────────

    def test_no_access_returns_empty(self) -> None:
        # reviewers only have viewer on F96_DIRECT subtree, not on F188
        self.assertEqual(self._roles(REVIEWERS, F188), [])

    def test_unknown_member_returns_empty(self) -> None:
        self.assertEqual(self._roles("user:nobody@test.authomize.com", F188), [])

    def test_unknown_resource_returns_empty(self) -> None:
        self.assertEqual(self._roles(RON, "folders/000000000000"), [])

    # ── deduplication ─────────────────────────────────────────────────────

    def test_no_duplicate_roles(self) -> None:
        roles = self._roles(RON, F93)
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
        for expected in [
            ORG, F767, F36,
            F96_DIRECT, F96_UNDER767,
            F188, F635, F495, F518, F837, F93, F361,
            P185, P20, P377,
        ]:
            self.assertIn(expected, resources)

    def test_ron_has_owner_on_org(self) -> None:
        self.assertIn("roles/owner", self._perms(RON)[ORG])

    def test_ron_inherits_owner_on_deep_folder(self) -> None:
        self.assertIn("roles/owner", self._perms(RON)[F93])

    def test_ron_billing_account_direct_only(self) -> None:
        # billing account has no hierarchy edge — direct role only
        self.assertEqual(self._perms(RON)[BILLING], ["roles/billing.admin"])

    # ── dev-manager ────────────────────────────────────────────────────────

    def test_dev_manager_accessible_resources(self) -> None:
        resources = set(self._perms(DEV_MANAGER).keys())
        self.assertIn(F635, resources)   # direct
        self.assertIn(F518, resources)   # child of F635
        self.assertIn(F837, resources)   # child of F635
        # billing account is not reachable via hierarchy
        self.assertNotIn(BILLING, resources)

    def test_dev_manager_roles_on_direct_resource(self) -> None:
        roles = self._perms(DEV_MANAGER)[F635]
        self.assertIn("roles/owner", roles)

    def test_dev_manager_inherited_roles_on_child(self) -> None:
        roles = self._perms(DEV_MANAGER)[F518]
        self.assertIn("roles/owner", roles)

    # ── reviewers (scoped to F96_DIRECT subtree) ──────────────────────────

    def test_reviewers_scoped_to_96505015065_direct_subtree(self) -> None:
        resources = set(self._perms(REVIEWERS).keys())
        # IAM binding is on F96_DIRECT (the direct child of org)
        self.assertIn(F96_DIRECT, resources)
        # F93 and F361 are children of F96_UNDER767, a different node
        self.assertNotIn(F93, resources)
        self.assertNotIn(F361, resources)
        # outside the subtree
        self.assertNotIn(F767, resources)
        self.assertNotIn(ORG, resources)

    def test_reviewers_role_is_viewer(self) -> None:
        for resource in self._perms(REVIEWERS).values():
            self.assertEqual(resource, ["roles/viewer"])

    # ── deduplication ─────────────────────────────────────────────────────

    def test_no_duplicate_roles_in_any_resource(self) -> None:
        for resource, roles in self._perms(RON).items():
            self.assertEqual(len(roles), len(set(roles)), f"duplicates in {resource}")


if __name__ == "__main__":
    unittest.main()
