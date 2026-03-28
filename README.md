# GCP Asset Graph

A Python tool for loading a [GCP Cloud Asset Inventory](https://cloud.google.com/asset-inventory/docs/overview) export into a directed graph, then querying IAM permissions and resource hierarchy.

## Project structure

| File | Purpose |
|---|---|
| `graph.py` | Generic directed graph — `Node`, `Edge`, `DiGraph` |
| `gcp_asset_graph.py` | Parses a `.jsonl` asset export, builds the graph, exposes query functions, and runs an interactive CLI |
| `sample_assets.jsonl` | Sample GCP asset export used by the tests and the CLI |
| `config.json` | Optional startup config (see below) |
| `graph.html` | Generated HTML visualisation (created on demand) |

## Demo

### Resource hierarchy (`sample_assets.jsonl`)

```
organizations/1066060271767
├── folders/36290848176
│   ├── folders/495694787245
│   └── projects/20671306372
├── folders/767216091627
│   ├── folders/188906894377
│   ├── folders/635215680011
│   │   ├── folders/518729943705
│   │   └── folders/837642324986
│   └── folders/96505015065
│       ├── folders/361332156337
│       └── folders/93198982071
├── projects/185023072868
└── projects/377145543109
```

### IAM assignments (direct grants only)

```
member                              resource                      roles
──────────────────────────────────  ────────────────────────────  ──────────────────────────────────────
ron@test.authomize.com              organizations/1066060271767   owner, resourcemanager.folderAdmin
                                    billingAccounts/01B2E0-…      billing.admin
dev-manager@...                     folders/767216091627          viewer
                                    folders/635215680011          owner, viewer
reviewers@test.authomize.com        folders/96505015065           viewer
exercise-fetcher@...                organizations/1066060271767   owner, browser, cloudasset.owner, …
```

Because roles inherit downward, `ron` (owner on the org) effectively has owner on every resource in the tree. `reviewers` (viewer on `folders/96505015065`) inherit viewer on its two child folders but have no access outside that subtree.

### Querying with Python

```python
from pathlib import Path
from gcp_asset_graph import build_graph_from_jsonl, effective_roles, all_permissions, PermissionIndex

g = build_graph_from_jsonl(Path("sample_assets.jsonl"))

# Roles a member holds on a specific resource (direct + inherited)
effective_roles(g, "user:ron@test.authomize.com", "folders/93198982071")
# → ['roles/owner', 'roles/resourcemanager.folderAdmin', 'roles/resourcemanager.folderEditor']

effective_roles(g, "group:reviewers@test.authomize.com", "folders/93198982071")
# → ['roles/viewer']

effective_roles(g, "group:reviewers@test.authomize.com", "folders/188906894377")
# → []  (outside the reviewers' subtree)

# Every resource a member can reach, mapped to their roles
perms = all_permissions(g, "serviceAccount:dev-manager@striking-arbor-264209.iam.gserviceaccount.com")
# perms["folders/635215680011"] → ['roles/owner', 'roles/viewer']  (direct)
# perms["folders/518729943705"] → ['roles/owner', 'roles/viewer']  (inherited)

# Pre-computed index for repeated lookups (O(1) after build)
index = PermissionIndex(g)
index.effective_roles("user:ron@test.authomize.com", "folders/518729943705")
# → ['roles/owner', 'roles/resourcemanager.folderAdmin', 'roles/resourcemanager.folderEditor']
```

### HTML visualisation

Running option `1` in the CLI writes `graph.html` and opens it in the browser. Resources (rectangles) are laid out as a depth-based tree; members (ellipses) float above. Hierarchy edges are solid grey; IAM edges are dashed orange — hover over an IAM edge to see the granted roles.

## How it works

Two kinds of edges are added to the graph:

- **Hierarchy** (`kind="hierarchy"`) — `parent → child`, derived from each asset's `ancestors` list.
- **IAM** (`kind="iam"`) — `member → resource`, derived from each asset's `iam_policy.bindings`. Roles are stored on the edge.

IAM roles are **inherited downward**: a role granted on an ancestor resource is implicitly granted on all descendants.

## Setup

Requires Python 3.10+. No external dependencies.

```bash
python gcp_asset_graph.py
```

## Interactive CLI

```
1 - Full graph          # opens graph.html in the browser
2 - Resource hierarchy  # print folder/project tree
3 - All permissions for a user
4 - All permissions on a resource
q - Quit
```

## config.json

Controls what is printed on startup:

```json
{
  "stats": true,               // print node/edge counts
  "edges": false,              // print every edge
  "folder_hierarchy": true,    // print folder tree
  "folder_hierarchy_root": "organizations/123"  // tree root (omit for full forest)
}
```

## Running tests

```bash
python -m unittest discover -v
```

- `test_graph.py` — unit tests for `DiGraph`, `Node`, `Edge`
- `test_assets_graph.py` — integration tests for hierarchy, effective roles, and permission queries against `sample_assets.jsonl`

## Public API (`gcp_asset_graph.py`)

| Function | Description |
|---|---|
| `build_graph_from_jsonl(path)` | Parse a `.jsonl` file and return a `DiGraph` |
| `effective_roles(g, member, resource)` | Roles a member holds on a resource (direct + inherited) |
| `all_permissions(g, member)` | All resources a member can access, mapped to their roles |
| `get_folder_hierarchy(g, root)` | `parent → [children]` dict for folder/org nodes |
| `show_folder_hierarchy(g, root)` | Indented string representation of the hierarchy |
| `PermissionIndex(g)` | Pre-computed index for O(1) permission lookups |
| `export_html(g, path)` | Write a pannable/zoomable SVG visualisation to an HTML file |
