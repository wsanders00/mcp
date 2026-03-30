from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

from install.models import ReadinessResult, ServerSpec


def _installer_module():
    return importlib.import_module("install.installer")


def _make_server_spec(**overrides: object) -> ServerSpec:
    values = {
        "id": "oci-api-mcp-server",
        "display_name": "OCI API MCP Server",
        "source_path": "src/oci-api-mcp-server",
        "install_mode": "package",
        "launch_mode": "console_script",
        "entrypoint": "oci-api-mcp",
        "launch_args": (),
        "python_version": "3.13",
        "requirements_path": None,
    }
    values.update(overrides)
    return ServerSpec(**values)


def test_run_install_orchestrates_runtime_readiness_and_render_steps(tmp_path: Path):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    script_spec = _make_server_spec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )
    registry = {
        package_spec.id: package_spec,
        script_spec.id: script_spec,
    }
    package_plan = type("Plan", (), {"spec": package_spec})()
    script_plan = type("Plan", (), {"spec": script_spec})()
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    blocked_result = ReadinessResult(server_id=script_spec.id, status="blocked", message="Blocked.")
    rendered = object()
    calls: list[tuple[object, ...]] = []

    def fake_load_registry(path: Path):
        calls.append(("load_registry", path))
        return registry

    def fake_resolve_selection(selection: str, loaded_registry: dict[str, ServerSpec]):
        calls.append(("resolve_selection", selection, loaded_registry))
        return [package_spec, script_spec]

    def fake_build_runtime_plan(spec: ServerSpec, root: Path):
        calls.append(("build_runtime_plan", spec.id, root))
        return package_plan if spec.id == package_spec.id else script_plan

    def fake_run_runtime_plan(plan):
        calls.append(("run_runtime_plan", plan.spec.id))
        return plan

    def fake_classify_runtime_readiness(plan, user_home=None):
        calls.append(("classify_runtime_readiness", plan.spec.id, user_home))
        return ready_result if plan.spec.id == package_spec.id else blocked_result

    def fake_render_install_artifacts(plans, readiness_results, root: Path, force: bool = False):
        calls.append(
            (
                "render_install_artifacts",
                tuple(plan.spec.id for plan in plans),
                tuple(result.status for result in readiness_results),
                root,
                force,
            )
        )
        return rendered

    result = installer.run_install(
        ["--servers", " oci-api-mcp-server , dbtools-mcp-server ", "--force"],
        repo_root=repo_root,
        load_registry_fn=fake_load_registry,
        resolve_selection_fn=fake_resolve_selection,
        build_runtime_plan_fn=fake_build_runtime_plan,
        run_runtime_plan_fn=fake_run_runtime_plan,
        classify_runtime_readiness_fn=fake_classify_runtime_readiness,
        render_install_artifacts_fn=fake_render_install_artifacts,
    )

    assert result.selection == "oci-api-mcp-server,dbtools-mcp-server"
    assert result.selected_server_ids == (package_spec.id, script_spec.id)
    assert result.runtime_plans == (package_plan, script_plan)
    assert result.readiness_results == (ready_result, blocked_result)
    assert result.render_output is rendered
    assert calls == [
        ("load_registry", repo_root / "install" / "servers.toml"),
        ("resolve_selection", "oci-api-mcp-server,dbtools-mcp-server", registry),
        ("build_runtime_plan", package_spec.id, repo_root),
        ("build_runtime_plan", script_spec.id, repo_root),
        ("run_runtime_plan", package_spec.id),
        ("classify_runtime_readiness", package_spec.id, None),
        ("run_runtime_plan", script_spec.id),
        ("classify_runtime_readiness", script_spec.id, None),
        (
            "render_install_artifacts",
            (package_spec.id, script_spec.id),
            ("ready", "blocked"),
            repo_root,
            True,
        ),
    ]


def test_installer_script_invokes_main_for_help_output():
    repo_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "install/installer.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Local MCP installer" in result.stdout
    assert "--servers" in result.stdout
    assert "--force" in result.stdout


def test_run_install_continues_when_runtime_provisioning_fails(tmp_path: Path):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    failing_spec = _make_server_spec(id="oci-pricing-mcp-server", python_version="3.11")
    ready_spec = _make_server_spec(
        id="oci-iot-mcp-server",
        source_path="src/oci-iot-mcp-server",
        entrypoint="oci-iot-mcp-server",
    )
    registry = {
        failing_spec.id: failing_spec,
        ready_spec.id: ready_spec,
    }
    failing_plan = type(
        "Plan",
        (),
        {
            "spec": failing_spec,
            "venv_dir": repo_root / "install" / "runtime" / failing_spec.id / "venv",
            "install_target": repo_root / failing_spec.source_path,
        },
    )()
    ready_plan = type(
        "Plan",
        (),
        {
            "spec": ready_spec,
            "venv_dir": repo_root / "install" / "runtime" / ready_spec.id / "venv",
            "install_target": repo_root / ready_spec.source_path,
        },
    )()
    ready_result = ReadinessResult(server_id=ready_spec.id, status="ready", message="Ready.")
    rendered = object()
    calls: list[tuple[object, ...]] = []

    def fake_load_registry(path: Path):
        calls.append(("load_registry", path))
        return registry

    def fake_resolve_selection(selection: str, loaded_registry: dict[str, ServerSpec]):
        calls.append(("resolve_selection", selection, loaded_registry))
        return [failing_spec, ready_spec]

    def fake_build_runtime_plan(spec: ServerSpec, root: Path):
        calls.append(("build_runtime_plan", spec.id, root))
        return failing_plan if spec.id == failing_spec.id else ready_plan

    def fake_run_runtime_plan(plan):
        calls.append(("run_runtime_plan", plan.spec.id))
        if plan.spec.id == failing_spec.id:
            raise RuntimeError("build failed")
        return plan

    def fake_classify_runtime_readiness(plan, user_home=None):
        calls.append(("classify_runtime_readiness", plan.spec.id, user_home))
        return ready_result

    def fake_render_install_artifacts(plans, readiness_results, root: Path, force: bool = False):
        calls.append(
            (
                "render_install_artifacts",
                tuple(plan.spec.id for plan in plans),
                tuple(result.status for result in readiness_results),
                root,
                force,
            )
        )
        return rendered

    result = installer.run_install(
        ["--servers", "oci-pricing-mcp-server,oci-iot-mcp-server"],
        repo_root=repo_root,
        load_registry_fn=fake_load_registry,
        resolve_selection_fn=fake_resolve_selection,
        build_runtime_plan_fn=fake_build_runtime_plan,
        run_runtime_plan_fn=fake_run_runtime_plan,
        classify_runtime_readiness_fn=fake_classify_runtime_readiness,
        render_install_artifacts_fn=fake_render_install_artifacts,
    )

    assert result.runtime_plans == (failing_plan, ready_plan)
    assert [readiness.status for readiness in result.readiness_results] == ["failed", "ready"]
    assert result.readiness_results[0].server_id == failing_spec.id
    assert "build failed" in result.readiness_results[0].message
    assert result.render_output is rendered
    assert calls == [
        ("load_registry", repo_root / "install" / "servers.toml"),
        ("resolve_selection", "oci-pricing-mcp-server,oci-iot-mcp-server", registry),
        ("build_runtime_plan", failing_spec.id, repo_root),
        ("build_runtime_plan", ready_spec.id, repo_root),
        ("run_runtime_plan", failing_spec.id),
        ("run_runtime_plan", ready_spec.id),
        ("classify_runtime_readiness", ready_spec.id, None),
        (
            "render_install_artifacts",
            (failing_spec.id, ready_spec.id),
            ("failed", "ready"),
            repo_root,
            False,
        ),
    ]
