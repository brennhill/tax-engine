# External Workspace Model Design

## Goal

Make the public repo external-first for real user workspaces while preserving the checked-in synthetic demo workspace. A user should be able to run the demo from the repo, but real tax data should default to `~/taxes/<year>/` instead of living under the repo tree.

## Why This Change Exists

The repo is now public-safe, but the current runtime contract still encourages storing real configs, raw documents, normalized facts, and outputs inside the repository under `years/<year>/`. That is the wrong default for a public tool because it mixes code and private tax data.

The external-first model changes the boundary:

- the repo ships engine code plus `years/demo-2025/`
- real workspaces live outside the repo by default
- users can still override the workspace path explicitly

This keeps the demo easy to run while making the safe path the normal path.

## Primary User Flows

### Built-In Demo

The built-in synthetic demo remains repo-local.

Example:

```bash
python3 -m tax_pipeline.run_year demo-2025
```

This uses:

- repo-local `years/demo-2025/`

and does not try to create or use `~/taxes/demo-2025/`.

### Default Real Workspace

When the user runs a numeric year without `--workspace`, the engine should default to:

```text
~/taxes/<year>/
```

Examples:

```bash
python3 -m tax_pipeline.scaffold_year 2025
python3 -m tax_pipeline.run_year 2025
```

Both should target:

```text
/Users/<user>/taxes/2025/
```

If the workspace does not exist yet, the tool should show the resolved path and prompt before creating it.

### Explicit Workspace Override

Advanced users can provide a custom workspace path:

```bash
python3 -m tax_pipeline.scaffold_year 2025 --workspace /custom/path
python3 -m tax_pipeline.run_year 2025 --workspace /custom/path
```

If `--workspace` is provided, the tool should use that path directly and not rewrite it to `~/taxes/<year>/`.

## Runtime Contract

### Separate Project Root and Workspace Root

The system should distinguish between:

- `project_root`
  - where code, docs, law specs, tests, and the built-in demo live
- `workspace_root`
  - where the selected year workspace lives

For demo runs:

- `workspace_root` is repo-local

For real runs:

- `workspace_root` is external by default

This is the key architectural shift. The runtime should stop assuming that a year workspace always lives under `project_root/years/<year>/`.

### Year Path Resolution

The path layer should be able to resolve all year-specific directories from a workspace root directly.

Examples:

- config files
- raw document buckets
- normalized facts
- derived facts
- outputs
- forms
- legal-audit outputs

The year-path object should preserve its current field names where possible, but it should derive them from `workspace_root` instead of hardcoding `project_root / "years" / <year>`.

### Demo Path Resolution

The repo keeps:

- `years/demo-2025/`

The runtime should treat this as a special built-in workspace. The demo path should continue to work exactly as it does today, and it should not be relocated or copied to `~/taxes/` just to run.

## CLI Design

### `run_year`

New supported shapes:

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.run_year 2025
python3 -m tax_pipeline.run_year 2025 --workspace /custom/path
```

Behavior:

- `demo-2025`
  - run repo-local demo workspace
- numeric year with no workspace
  - resolve to `~/taxes/<year>/`
- numeric year with `--workspace`
  - use explicit path

### `scaffold_year`

New supported shapes:

```bash
python3 -m tax_pipeline.scaffold_year 2025
python3 -m tax_pipeline.scaffold_year 2025 --workspace /custom/path
```

Behavior:

- numeric year with no workspace
  - default to `~/taxes/<year>/`
- `--workspace`
  - use explicit path

The scaffold command should stay focused on real workspaces. The checked-in demo is already provided and should not be re-scaffolded.

## Prompting Behavior

### Missing External Workspace

If a numeric-year target workspace does not exist yet:

1. resolve the exact target path
2. display it clearly
3. prompt before creating it

Example:

```text
Workspace for 2025 does not exist yet: /Users/<user>/taxes/2025
Create it now? [y/N]
```

This prompt should happen only when the command would otherwise create the workspace.

### Existing Workspace

If the workspace already exists:

- use it without extra prompting

### Explicit `--workspace`

If the user passes `--workspace`, the command should honor the explicit path and only prompt if creation is required.

## README and Public-Facing Guidance

The public docs should lead with two flows:

### Try the Demo

```bash
python3 -m tax_pipeline.run_year demo-2025
```

### Create a Real Workspace

```bash
python3 -m tax_pipeline.scaffold_year 2025
python3 -m tax_pipeline.run_year 2025
```

And explain that real workspaces default to:

```text
~/taxes/<year>/
```

The docs should make it clear that:

- the repo should remain code + demo only
- real user tax data should live outside the repo

## Error Handling

### Invalid Demo Name

If the user passes a non-numeric year token that is not a supported demo workspace, the runtime should fail clearly.

### Missing Workspace Files

Once a workspace is selected, all existing structured-input validation should continue to work, but the paths in the errors should reference the external workspace location rather than implying repo-local storage.

### No Silent Fallback to Repo-Local Real Years

For numeric years, the runtime should not silently decide to use `project_root/years/<year>/` as a hidden fallback for real workspaces. That would undermine the external-first contract.

The only repo-local year workspace that should remain special is the synthetic demo.

## Testing Strategy

This change needs tests for:

- demo resolution stays repo-local
- numeric year defaults to `~/taxes/<year>/`
- `--workspace` overrides the default
- scaffold can create an external workspace
- run-time prompts before creating a missing external workspace
- existing repo-local demo flows remain green
- no real-workspace outputs are written into the repo when the default external path is used

## Non-Goals

This phase does not include:

- packaging the repo as a full installed CLI
- a persistent global config system
- generalizing beyond the current year support model
- widening supported filing postures or providers

## Recommended Implementation Direction

1. update path resolution so `YearPaths` can be built from an explicit workspace root
2. add runtime helpers that choose between demo workspace, default external workspace, and explicit override
3. update `run_year` and `scaffold_year` argument parsing to expose the new contract
4. update docs to make the external-first flow the primary public path
5. preserve current demo behavior exactly
