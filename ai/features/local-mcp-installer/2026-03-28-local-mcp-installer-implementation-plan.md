# Local MCP Installer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fork-only installer under `install/` that lets a user choose Python-based MCP servers from this repo, installs each selected server into its own runtime, and generates Codex and VS Code artifacts so agents can start those servers on demand.

**Architecture:** Keep all implementation under `install/` with small Python modules for registry parsing, runtime provisioning, readiness checks, and artifact rendering. Install each selected server into an isolated runtime to avoid dependency conflicts, then expose only stable wrapper scripts to generated Codex/VS Code config.

**Tech Stack:** Python 3.13, stdlib (`argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`, `tomllib`), `uv`, pytest

---

## Scope

**In scope**

- Add fork-only installer code under `install/`.
- Add a checked-in server registry for supported Python-based repo servers.
- Prompt for `all` or a selected subset of supported repo servers.
- Build one runtime per selected server under `install/runtime/<server-id>/`.
- Support package-mode and script-mode server installs from local repo paths only.
- Generate stable wrapper scripts under `install/generated/bin/`.
- Generate Codex registration commands under `install/generated/codex/`.
- Generate a VS Code `mcp.json` under `install/generated/vscode/`.
- Generate readiness reports that classify selected servers as `ready`, `blocked`, or `failed`.
- Keep blocked servers such as `oracle-db-doc-mcp-server` out of generated agent config until prerequisites are satisfied.

**Out of scope**

- Installing any server not sourced from this repo checkout.
- Supporting `oracle-db-mcp-java-toolkit` in the initial implementation.
- Auto-editing `~/.codex` or VS Code settings.
- Refactoring non-IoT server source code.
- Adding long-lived daemon/service management.

## File Structure

**Create**

- `install/__init__.py`
  - Package marker for installer-local imports in tests.
- `install/models.py`
  - Dataclasses and enums for server specs, selection results, launch/bootstrap metadata, wrappers, and readiness statuses.
- `install/registry.py`
  - Loads `servers.toml`, validates metadata, and resolves `all` or explicit selections.
- `install/runtime_ops.py`
  - Creates per-server runtimes and installs package-mode or script-mode servers from local repo paths.
- `install/render.py`
  - Renders wrappers, Codex command scripts, VS Code `mcp.json`, and readiness summaries.
- `install/readiness.py`
  - Performs install and prerequisite checks and determines `ready`/`blocked`/`failed`.
- `install/installer.py`
  - CLI entry point that orchestrates prompting, installation, rendering, and reporting.
- `install/servers.toml`
  - Checked-in registry of installer-supported Python repo servers.
- `install/templates/wrapper.sh.tmpl`
  - Shell wrapper template for one selected server.
- `install/templates/codex_add.sh.tmpl`
  - Template for generated `codex mcp add` commands.
- `install/templates/vscode_mcp.json.tmpl`
  - Template for generated VS Code `mcp.json`.
- `install/templates/report.md.tmpl`
  - Template for human-readable install/readiness summary.
- `install/README.md`
  - Fork-only installer usage, Codex setup, VS Code setup, and prerequisite notes.
- `install/tests/conftest.py`
  - Shared fixtures for temporary roots, fake subprocess runners, and sample registry entries.
- `install/tests/test_registry.py`
  - Tests for registry parsing and selection resolution.
- `install/tests/test_installer_cli.py`
  - Tests for CLI argument handling and interactive prompting.
- `install/tests/test_runtime_ops.py`
  - Tests for per-server runtime provisioning commands and path layout.
- `install/tests/test_render.py`
  - Tests for wrapper generation and rendered Codex/VS Code artifacts.
- `install/tests/test_readiness.py`
  - Tests for `ready`/`blocked`/`failed` classification, especially `oracle-db-doc-mcp-server`.
- `install/tests/test_installer_flow.py`
  - End-to-end orchestration tests with a fake command runner and temp output tree.

**Modify**

- `.gitignore`
  - Ignore installer output and runtime directories while keeping installer code tracked.

## Registry Entries Required

Populate `install/servers.toml` with entries for every currently supported Python-based repo server:

- `dbtools-mcp-server`
- `mysql-mcp-server`
- `oci-api-mcp-server`
- `oci-cloud-guard-mcp-server`
- `oci-cloud-mcp-server`
- `oci-compute-instance-agent-mcp-server`
- `oci-compute-mcp-server`
- `oci-database-mcp-server`
- `oci-faaas-mcp-server`
- `oci-identity-mcp-server`
- `oci-iot-mcp-server`
- `oci-limits-mcp-server`
- `oci-load-balancer-mcp-server`
- `oci-logging-mcp-server`
- `oci-migration-mcp-server`
- `oci-monitoring-mcp-server`
- `oci-network-load-balancer-mcp-server`
- `oci-networking-mcp-server`
- `oci-object-storage-mcp-server`
- `oci-pricing-mcp-server`
- `oci-recovery-mcp-server`
- `oci-registry-mcp-server`
- `oci-resource-search-mcp-server`
- `oci-usage-mcp-server`
- `oracle-db-doc-mcp-server`

Use explicit metadata for the known edge cases:

- `dbtools-mcp-server`
  - `install_mode = "script"`
  - `launch_mode = "python_script"`
  - `requirements_path = "src/dbtools-mcp-server/requirements.txt"`
  - `entrypoint = "src/dbtools-mcp-server/dbtools-mcp-server.py"`
- `oracle-db-doc-mcp-server`
  - `install_mode = "script"`
  - `launch_mode = "python_script"`
  - `requirements_path = "src/oracle-db-doc-mcp-server/requirements.txt"`
  - `entrypoint = "src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py"`
  - `launch_args = ["mcp"]`
  - readiness rule requires a built docs index before agent config emission

## Execution Notes

- Follow `@superpowers/test-driven-development` discipline for each task.
- Use `@superpowers/verification-before-completion` before claiming the installer is ready.
- Keep runtime creation, readiness, and rendering separated so each unit is testable in isolation.
- Do not modify any server source outside `src/oci-iot-mcp-server`; prefer installer-owned wrappers and registry metadata instead.

## Chunk 1: Registry And CLI Foundation

### Task 1: Add installer scaffolding, ignore rules, and registry resolution

**Files:**

- Modify: `.gitignore`
- Create: `install/__init__.py`
- Create: `install/models.py`
- Create: `install/registry.py`
- Create: `install/servers.toml`
- Create: `install/tests/conftest.py`
- Create: `install/tests/test_registry.py`

- [ ] **Step 1: Write the failing registry tests**

```python
from install.registry import load_registry, resolve_selection


def test_resolve_all_returns_supported_python_server_ids_only():
    registry = load_registry("install/servers.toml")

    selected = resolve_selection(registry, "all")

    ids = {item.id for item in selected}
    assert "oci-iot-mcp-server" in ids
    assert "oracle-db-doc-mcp-server" in ids
    assert "dbtools-mcp-server" in ids
    assert "oracle-db-mcp-java-toolkit" not in ids


def test_registry_rejects_entry_without_launch_metadata(tmp_path):
    registry_file = tmp_path / "servers.toml"
    registry_file.write_text(
        """
        [servers.bad]
        id = "bad"
        display_name = "Bad"
        source_path = "src/bad"
        install_mode = "package"
        """
    )

    try:
        load_registry(registry_file)
    except ValueError as exc:
        assert "launch_mode" in str(exc)
    else:
        raise AssertionError("Expected ValueError for incomplete server metadata")
```

- [ ] **Step 2: Run the registry test to verify it fails**

Run from repo root:

```bash
pytest install/tests/test_registry.py::test_resolve_all_returns_supported_python_server_ids_only -q
```

Expected: FAIL with `ModuleNotFoundError` for `install.registry` or missing `load_registry`.

- [ ] **Step 3: Add ignore rules, installer models, and registry parsing**

Update `.gitignore`:

```gitignore
/install/generated/
/install/runtime/
```

Create focused installer models:

```python
# install/models.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServerSpec:
    id: str
    display_name: str
    source_path: str
    install_mode: str
    launch_mode: str
    entrypoint: str
    launch_args: list[str] = field(default_factory=list)
    python_version: str = "3.13"
    requirements_path: str | None = None
    readiness_check: str = "basic"
    env_hints: list[str] = field(default_factory=list)
    notes: str | None = None
```

Create `install/registry.py` so it:

- loads TOML with `tomllib`
- validates required fields
- returns `ServerSpec` instances
- resolves `all` to every registry entry except unsupported non-Python servers
- resolves comma-separated explicit ids deterministically
- preserves optional `launch_args` metadata for script-mode edge cases such as `oracle-db-doc-mcp-server`

Seed `install/servers.toml` with explicit entries for the 25 supported Python-based repo servers listed in
the **Registry Entries Required** section above.

- [ ] **Step 4: Re-run the registry tests to verify they pass**

Run:

```bash
pytest install/tests/test_registry.py -q
```

Expected: PASS with both registry tests green.

- [ ] **Step 5: Commit the registry foundation**

```bash
git add .gitignore install/__init__.py install/models.py install/registry.py install/servers.toml install/tests/conftest.py install/tests/test_registry.py
git commit -s -m "feat: add local installer registry foundation"
```

### Task 2: Add CLI parsing and interactive selection flow

**Files:**

- Create: `install/installer.py`
- Create: `install/tests/test_installer_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

```python
from install.installer import build_parser, choose_selection


def test_parser_accepts_servers_argument():
    parser = build_parser()

    args = parser.parse_args(["--servers", "all"])

    assert args.servers == "all"


def test_choose_selection_prompts_when_servers_missing(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "oci-iot-mcp-server,oci-api-mcp-server")

    selected = choose_selection(None)

    assert selected == "oci-iot-mcp-server,oci-api-mcp-server"
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run:

```bash
pytest install/tests/test_installer_cli.py -q
```

Expected: FAIL because `build_parser` and `choose_selection` do not exist yet.

- [ ] **Step 3: Implement the CLI shell without install side effects**

Create `install/installer.py` with:

```python
import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--servers", help="Comma-separated server ids or 'all'")
    parser.add_argument("--force", action="store_true", help="Rebuild selected runtimes even if they exist")
    return parser


def choose_selection(raw_value: str | None) -> str:
    if raw_value:
        return raw_value
    return input("Select MCP servers to install (comma-separated ids or 'all'): ").strip()
```

Keep orchestration minimal in this task. Do not add runtime or rendering logic yet.

- [ ] **Step 4: Re-run the CLI tests to verify they pass**

Run:

```bash
pytest install/tests/test_installer_cli.py -q
```

Expected: PASS with both CLI tests green.

- [ ] **Step 5: Commit the CLI selection flow**

```bash
git add install/installer.py install/tests/test_installer_cli.py
git commit -s -m "feat: add local installer selection cli"
```

## Chunk 2: Per-Server Runtime Provisioning And Readiness

### Task 3: Add per-server runtime provisioning for package and script modes

**Files:**

- Create: `install/runtime_ops.py`
- Create: `install/tests/test_runtime_ops.py`
- Modify: `install/installer.py`

- [ ] **Step 1: Write the failing runtime command tests**

```python
from install.models import ServerSpec
from install.runtime_ops import build_runtime_plan


def test_package_server_runtime_plan_targets_dedicated_runtime():
    spec = ServerSpec(
        id="oci-iot-mcp-server",
        display_name="OCI IoT MCP Server",
        source_path="src/oci-iot-mcp-server",
        install_mode="package",
        launch_mode="console_script",
        entrypoint="oracle.oci-iot-mcp-server",
    )

    plan = build_runtime_plan(spec, repo_root="/repo")

    assert plan.runtime_dir.endswith("install/runtime/oci-iot-mcp-server")
    assert any("uv venv" in " ".join(cmd) for cmd in plan.commands)
    assert any("./src/oci-iot-mcp-server" in " ".join(cmd) for cmd in plan.commands)


def test_script_server_runtime_plan_uses_requirements_file():
    spec = ServerSpec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )

    plan = build_runtime_plan(spec, repo_root="/repo")

    assert any("-r" in cmd for cmd in plan.commands[1])
    assert "dbtools-mcp-server" in plan.runtime_dir
```

- [ ] **Step 2: Run the runtime test to verify it fails**

Run:

```bash
pytest install/tests/test_runtime_ops.py::test_package_server_runtime_plan_targets_dedicated_runtime -q
```

Expected: FAIL because `build_runtime_plan` does not exist.

- [ ] **Step 3: Implement per-server runtime planning and execution helpers**

Create `install/runtime_ops.py` with:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePlan:
    runtime_dir: str
    commands: list[list[str]]


def build_runtime_plan(spec, repo_root: str) -> RuntimePlan:
    runtime_dir = str(Path(repo_root) / "install" / "runtime" / spec.id)
    python_bin = str(Path(runtime_dir) / "bin" / "python")
    commands = [["uv", "venv", "--python", spec.python_version, runtime_dir]]

    if spec.install_mode == "package":
        commands.append(["uv", "pip", "install", "--python", python_bin, str(Path(repo_root) / spec.source_path)])
    else:
        commands.append(
            ["uv", "pip", "install", "--python", python_bin, "-r", str(Path(repo_root) / spec.requirements_path)]
        )

    return RuntimePlan(runtime_dir=runtime_dir, commands=commands)
```

Also add a thin `run_runtime_plan(...)` helper that executes each command with `subprocess.run(..., check=True)`.

- [ ] **Step 4: Re-run the runtime tests to verify they pass**

Run:

```bash
pytest install/tests/test_runtime_ops.py -q
```

Expected: PASS with package-mode and script-mode runtime planning green.

- [ ] **Step 5: Commit per-server runtime provisioning**

```bash
git add install/runtime_ops.py install/tests/test_runtime_ops.py install/installer.py
git commit -s -m "feat: add per-server installer runtimes"
```

### Task 4: Add readiness classification and blocked-server handling

**Files:**

- Create: `install/readiness.py`
- Create: `install/tests/test_readiness.py`
- Modify: `install/models.py`
- Modify: `install/installer.py`

- [ ] **Step 1: Write the failing readiness tests**

```python
from install.models import ServerSpec
from install.readiness import classify_server


def test_oracle_db_doc_without_index_is_blocked(tmp_path):
    spec = ServerSpec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        launch_args=["mcp"],
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
        readiness_check="oracle_db_doc_index",
    )

    result = classify_server(spec, repo_root=tmp_path, runtime_dir=tmp_path / "runtime")

    assert result.status == "blocked"
    assert "index" in result.message.lower()


def test_basic_ready_server_is_marked_ready(tmp_path):
    spec = ServerSpec(
        id="oci-iot-mcp-server",
        display_name="OCI IoT MCP Server",
        source_path="src/oci-iot-mcp-server",
        install_mode="package",
        launch_mode="console_script",
        entrypoint="oracle.oci-iot-mcp-server",
        readiness_check="basic",
    )

    runtime_dir = tmp_path / "runtime"
    (runtime_dir / "bin").mkdir(parents=True)
    (runtime_dir / "bin" / "oracle.oci-iot-mcp-server").write_text("#!/bin/sh\n")

    result = classify_server(spec, repo_root=tmp_path, runtime_dir=runtime_dir)

    assert result.status == "ready"


def test_script_server_is_marked_ready_when_runtime_python_and_entrypoint_exist(tmp_path):
    spec = ServerSpec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )

    runtime_dir = tmp_path / "runtime"
    (runtime_dir / "bin").mkdir(parents=True)
    (runtime_dir / "bin" / "python").write_text("#!/bin/sh\n")
    (tmp_path / "src" / "dbtools-mcp-server").mkdir(parents=True)
    (tmp_path / "src" / "dbtools-mcp-server" / "dbtools-mcp-server.py").write_text("print('ok')\n")

    result = classify_server(spec, repo_root=tmp_path, runtime_dir=runtime_dir)

    assert result.status == "ready"
```

- [ ] **Step 2: Run the readiness tests to verify they fail**

Run:

```bash
pytest install/tests/test_readiness.py -q
```

Expected: FAIL because `classify_server` and result models do not exist yet.

- [ ] **Step 3: Implement readiness results and prerequisite checks**

Extend `install/models.py`:

```python
@dataclass(frozen=True)
class ReadinessResult:
    server_id: str
    status: str
    message: str
```

Create `install/readiness.py` so it:

- marks package-mode servers `ready` when their console-script launch target exists in the runtime
- marks script-mode servers `ready` when the runtime interpreter exists and the repo entrypoint exists
- marks `oracle-db-doc-mcp-server` `blocked` when no docs index is present
- returns `failed` when expected runtime artifacts are missing after install

Keep the first implementation simple and deterministic. Do not attempt to start real servers in this task.

- [ ] **Step 4: Re-run the readiness tests to verify they pass**

Run:

```bash
pytest install/tests/test_readiness.py -q
```

Expected: PASS with `ready` and `blocked` classifications green.

- [ ] **Step 5: Commit readiness classification**

```bash
git add install/models.py install/readiness.py install/tests/test_readiness.py install/installer.py
git commit -s -m "feat: add installer readiness classification"
```

## Chunk 3: Agent Artifacts, Reporting, And Docs

### Task 5: Generate wrappers, Codex commands, VS Code config, and readiness reports

**Files:**

- Create: `install/render.py`
- Create: `install/templates/wrapper.sh.tmpl`
- Create: `install/templates/codex_add.sh.tmpl`
- Create: `install/templates/vscode_mcp.json.tmpl`
- Create: `install/templates/report.md.tmpl`
- Create: `install/tests/test_render.py`
- Create: `install/tests/test_installer_flow.py`
- Modify: `install/installer.py`

- [ ] **Step 1: Write the failing render and flow tests**

```python
from install.models import ReadinessResult, ServerSpec
from install.render import render_vscode_config, render_wrapper


def test_render_wrapper_uses_server_runtime_path(tmp_path):
    spec = ServerSpec(
        id="oci-iot-mcp-server",
        display_name="OCI IoT MCP Server",
        source_path="src/oci-iot-mcp-server",
        install_mode="package",
        launch_mode="console_script",
        entrypoint="oracle.oci-iot-mcp-server",
    )

    wrapper = render_wrapper(spec, repo_root=tmp_path)

    assert "install/runtime/oci-iot-mcp-server" in wrapper
    assert "oracle.oci-iot-mcp-server" in wrapper


def test_render_wrapper_includes_script_launch_args(tmp_path):
    spec = ServerSpec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        launch_args=["mcp"],
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
    )

    wrapper = render_wrapper(spec, repo_root=tmp_path)

    assert "oracle-db-doc-mcp-server.py" in wrapper
    assert " mcp " in wrapper or wrapper.rstrip().endswith(" mcp")


def test_vscode_config_includes_ready_servers_only():
    specs = {
        "oci-iot-mcp-server": ServerSpec(
            id="oci-iot-mcp-server",
            display_name="OCI IoT MCP Server",
            source_path="src/oci-iot-mcp-server",
            install_mode="package",
            launch_mode="console_script",
            entrypoint="oracle.oci-iot-mcp-server",
        ),
        "oracle-db-doc-mcp-server": ServerSpec(
            id="oracle-db-doc-mcp-server",
            display_name="Oracle DB Doc MCP Server",
            source_path="src/oracle-db-doc-mcp-server",
            install_mode="script",
            launch_mode="python_script",
            entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
            launch_args=["mcp"],
            requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
        ),
    }
    readiness = {
        "oci-iot-mcp-server": ReadinessResult("oci-iot-mcp-server", "ready", "ok"),
        "oracle-db-doc-mcp-server": ReadinessResult("oracle-db-doc-mcp-server", "blocked", "index missing"),
    }

    config = render_vscode_config(specs, readiness, repo_root="/repo")

    assert "oci-iot-mcp-server" in config["servers"]
    assert "oracle-db-doc-mcp-server" not in config["servers"]
```

- [ ] **Step 2: Run the render test to verify it fails**

Run:

```bash
pytest install/tests/test_render.py::test_vscode_config_includes_ready_servers_only -q
```

Expected: FAIL because rendering helpers do not exist yet.

- [ ] **Step 3: Implement rendering and installer orchestration**

Create `install/render.py` so it:

- renders one wrapper per ready server into `install/generated/bin/<server-id>`
- renders wrappers from `entrypoint` plus any `launch_args` metadata so script-mode servers launch correctly
- renders one Codex command script containing `codex mcp add <server-id> -- <wrapper-path>`
- renders one VS Code `mcp.json` with only ready servers
- renders one markdown summary report with `ready`, `blocked`, and `failed` sections

Update `install/installer.py` so `main()` performs:

1. parse args
2. choose selection
3. load registry
4. resolve selected specs
5. build and run each server runtime plan
6. classify readiness for each selected server
7. render wrappers and agent artifacts for ready servers only
8. write reports under `install/generated/reports/`

Keep all subprocess calls inside installer-owned helpers so tests can monkeypatch them cleanly.

- [ ] **Step 4: Re-run render and flow tests to verify they pass**

Run:

```bash
pytest install/tests/test_render.py install/tests/test_installer_flow.py -q
```

Expected: PASS with wrapper generation and config exclusion behavior green.

- [ ] **Step 5: Commit generated-artifact orchestration**

```bash
git add install/render.py install/templates/wrapper.sh.tmpl install/templates/codex_add.sh.tmpl install/templates/vscode_mcp.json.tmpl install/templates/report.md.tmpl install/tests/test_render.py install/tests/test_installer_flow.py install/installer.py
git commit -s -m "feat: generate local installer agent artifacts"
```

### Task 6: Document manual Codex and VS Code setup and verify the full installer test suite

**Files:**

- Create: `install/README.md`
- Modify: `install/tests/test_installer_flow.py`

- [ ] **Step 1: Write the failing documentation/report test**

```python
from pathlib import Path


def test_summary_report_includes_codex_and_vscode_next_steps(tmp_path):
    report = Path(tmp_path / "report.md")
    report.write_text(
        """
        ## Next Steps
        - Codex:
        - VS Code:
        """
    )

    text = report.read_text()
    assert "Codex" in text
    assert "VS Code" in text
```

Use this as a placeholder assertion only if the flow test suite still lacks coverage that the generated
human-readable output explains the manual next steps. If the report content is already covered by
`test_installer_flow.py`, replace this with a more specific assertion inside that existing file rather than
creating a redundant new test file.

- [ ] **Step 2: Run the targeted flow/doc tests to verify they fail if the instructions are missing**

Run:

```bash
pytest install/tests/test_installer_flow.py -q
```

Expected: FAIL until the generated summary or README includes the manual setup instructions.

- [ ] **Step 3: Write the installer README and final user-facing instructions**

Create `install/README.md` covering:

- prerequisites (`uv`, Python 3.13, local repo checkout)
- how to run the installer interactively
- how to run the installer non-interactively with `--servers`
- what `all` means
- where runtimes, wrappers, and generated artifacts are written
- how to register ready servers in Codex using the generated script
- how to use the generated VS Code `mcp.json`
- how blocked servers such as `oracle-db-doc-mcp-server` are reported and remediated

- [ ] **Step 4: Run the full installer test suite**

Run:

```bash
pytest install/tests -q
```

Expected: PASS with all installer-local tests green.

- [ ] **Step 5: Commit the README and final test coverage**

```bash
git add install/README.md install/tests/test_installer_flow.py
git commit -s -m "docs: add local installer usage guide"
```

## Final Verification Checklist

Before claiming the implementation is complete, run all of these from the repo root:

```bash
pytest install/tests -q
python install/installer.py --servers oci-iot-mcp-server
python install/installer.py --servers all
git status --short
```

Expected:

- installer-local tests pass
- the installer creates per-server runtimes under `install/runtime/<server-id>/`
- wrappers appear under `install/generated/bin/`
- Codex and VS Code artifacts appear under `install/generated/codex/` and `install/generated/vscode/`
- blocked servers are reported clearly and omitted from generated agent config
- no non-IoT server source files are modified
