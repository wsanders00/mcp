from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from install.models import ServerSpec


def _runtime_ops_module():
    return importlib.import_module("install.runtime_ops")


def _make_server_spec(**overrides: object) -> ServerSpec:
    values = {
        "id": "oci-api-mcp-server",
        "display_name": "OCI API MCP Server",
        "source_path": "src/oci-api-mcp-server",
        "install_mode": "package",
        "launch_mode": "console_script",
        "entrypoint": "oracle.oci-api-mcp-server",
        "python_version": "3.13",
        "requirements_path": None,
    }
    values.update(overrides)
    return ServerSpec(**values)


def test_build_runtime_plan_for_package_server_uses_local_package_path(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    spec = _make_server_spec()

    plan = runtime_ops.build_runtime_plan(spec, repo_root)

    assert plan.spec == spec
    assert plan.repo_root == repo_root
    assert plan.runtime_root == repo_root / "install" / "runtime"
    assert plan.server_runtime_dir == plan.runtime_root / spec.id
    assert plan.venv_dir == plan.server_runtime_dir / "venv"
    assert plan.python_path == plan.venv_dir / "bin" / "python"
    assert plan.install_target == repo_root / spec.source_path


def test_build_runtime_plan_for_script_server_uses_requirements_file(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    spec = _make_server_spec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
    )

    plan = runtime_ops.build_runtime_plan(spec, repo_root)

    assert plan.runtime_root == repo_root / "install" / "runtime"
    assert plan.server_runtime_dir == plan.runtime_root / spec.id
    assert plan.venv_dir == plan.server_runtime_dir / "venv"
    assert plan.python_path == plan.venv_dir / "bin" / "python"
    assert plan.install_target == repo_root / "src/oracle-db-doc-mcp-server/requirements.txt"


def test_run_runtime_plan_executes_uv_commands_for_package_server(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    plan = runtime_ops.build_runtime_plan(_make_server_spec(), repo_root)
    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_runner(command: list[str], cwd: Path) -> None:
        calls.append((tuple(command), cwd))

    runtime_ops.run_runtime_plan(plan, command_runner=fake_runner)

    assert calls == [
        (
            (
                "uv",
                "venv",
                str(plan.venv_dir),
                "--python",
                plan.spec.python_version,
                "--allow-existing",
            ),
            repo_root,
        ),
        (
            ("uv", "pip", "install", "--python", str(plan.python_path), str(plan.install_target)),
            repo_root,
        ),
    ]


def test_run_runtime_plan_executes_uv_commands_for_script_server(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    plan = runtime_ops.build_runtime_plan(
        _make_server_spec(
            id="dbtools-mcp-server",
            display_name="DBTools MCP Server",
            source_path="src/dbtools-mcp-server",
            install_mode="script",
            launch_mode="python_script",
            entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
            requirements_path="src/dbtools-mcp-server/requirements.txt",
        ),
        repo_root,
    )
    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_runner(command: list[str], cwd: Path) -> None:
        calls.append((tuple(command), cwd))

    runtime_ops.run_runtime_plan(plan, command_runner=fake_runner)

    assert calls == [
        (
            (
                "uv",
                "venv",
                str(plan.venv_dir),
                "--python",
                plan.spec.python_version,
                "--allow-existing",
            ),
            repo_root,
        ),
        (
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(plan.python_path),
                "-r",
                str(plan.install_target),
            ),
            repo_root,
        ),
    ]


def test_build_runtime_plan_rejects_script_server_without_requirements_path(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    spec = _make_server_spec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path=None,
    )

    with pytest.raises(ValueError, match="requires a requirements_path"):
        runtime_ops.build_runtime_plan(spec, repo_root)


def test_build_runtime_plan_rejects_unsupported_install_mode(tmp_path: Path):
    runtime_ops = _runtime_ops_module()
    repo_root = tmp_path / "repo"
    spec = _make_server_spec(install_mode="npm")

    with pytest.raises(ValueError, match="Unsupported install mode"):
        runtime_ops.build_runtime_plan(spec, repo_root)
