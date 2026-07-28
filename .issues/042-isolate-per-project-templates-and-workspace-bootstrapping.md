# Ticket 042: Isolate Per-Project Templates and Implement Workspace Bootstrapping

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK)

## Question

How should we update `LocalWorkspaceStorage` in `src/project/storage.py` and project initialization in `src/project/environment.py` to resolve templates from `<base_path>/templates/` and auto-bootstrap missing master templates from the repository `templates/` folder on project load?

## Reference Standard

- Johor JBU CLI `docs/project_centric_architecture.md`
- `C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV\src\project\storage.py`

## Summary of Work

1. Update `LocalWorkspaceStorage.__init__` in `src/project/storage.py` so `self._templates_dir` defaults to `self._root_path / "templates"`.
2. Add template bootstrapping logic (`ensure_project_templates` or `_initialize_project_workspace`) to copy missing master seed templates from `config.GLOBAL_TEMPLATES_DIR` into `<base_path>/templates/`.
3. Update `create_project_environment` and project creation in `src/project/environment.py` / `src/workflow_cli.py` to trigger workspace template bootstrapping.
4. Perform dead code cleanup to remove redundant template resolution logic across `src/`.
5. Update unit tests in `tests/` to verify template copying and resolution from project workspace root.
