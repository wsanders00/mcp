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


def _make_plan(spec: ServerSpec, repo_root: Path):
    return type(
        "Plan",
        (),
        {
            "spec": spec,
            "repo_root": repo_root,
            "server_runtime_dir": repo_root / "install" / "runtime" / spec.id,
            "venv_dir": repo_root / "install" / "runtime" / spec.id / "venv",
            "python_path": repo_root / "install" / "runtime" / spec.id / "venv" / "bin" / "python",
            "install_target": repo_root / spec.source_path,
        },
    )()


def _make_render_output(repo_root: Path, *wrapper_ids: str):
    return type(
        "RenderOutput",
        (),
        {
            "generated_root": repo_root / "install" / "generated",
            "wrapper_paths": tuple(
                repo_root / "install" / "generated" / "wrappers" / f"{server_id}.sh"
                for server_id in wrapper_ids
            ),
            "codex_example_path": repo_root / "install" / "generated" / "examples" / "codex.example.json",
            "vscode_example_path": repo_root / "install" / "generated" / "examples" / "vscode.mcp.json",
            "report_markdown_path": repo_root / "install" / "generated" / "reports" / "install-report.md",
            "report_json_path": repo_root / "install" / "generated" / "reports" / "install-report.json",
        },
    )()


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


def test_run_install_prints_general_summary_by_default(tmp_path: Path, capsys):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    blocked_spec = _make_server_spec(
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
        blocked_spec.id: blocked_spec,
    }
    package_plan = type("Plan", (), {"spec": package_spec})()
    blocked_plan = type("Plan", (), {"spec": blocked_spec})()
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    blocked_result = ReadinessResult(server_id=blocked_spec.id, status="blocked", message="Blocked.")
    render_output = type(
        "RenderOutput",
        (),
        {
            "generated_root": repo_root / "install" / "generated",
            "wrapper_paths": (repo_root / "install" / "generated" / "wrappers" / f"{package_spec.id}.sh",),
            "codex_example_path": repo_root / "install" / "generated" / "examples" / "codex.example.json",
            "vscode_example_path": repo_root / "install" / "generated" / "examples" / "vscode.mcp.json",
            "report_markdown_path": repo_root / "install" / "generated" / "reports" / "install-report.md",
            "report_json_path": repo_root / "install" / "generated" / "reports" / "install-report.json",
        },
    )()

    installer.run_install(
        ["--servers", "oci-api-mcp-server,dbtools-mcp-server"],
        repo_root=repo_root,
        load_registry_fn=lambda _path: registry,
        resolve_selection_fn=lambda _selection, _registry: [package_spec, blocked_spec],
        build_runtime_plan_fn=lambda spec, _root: package_plan if spec.id == package_spec.id else blocked_plan,
        run_runtime_plan_fn=lambda plan: plan,
        classify_runtime_readiness_fn=(
            lambda plan, user_home=None: ready_result if plan.spec.id == package_spec.id else blocked_result
        ),
        render_install_artifacts_fn=lambda *_args, **_kwargs: render_output,
    )

    captured = capsys.readouterr()

    assert "Selected servers: oci-api-mcp-server, dbtools-mcp-server" in captured.out
    assert "Ready: 1  Blocked: 1  Failed: 0" in captured.out
    assert str(render_output.report_markdown_path) in captured.out
    assert captured.err == ""


def test_run_install_silent_flag_suppresses_output(tmp_path: Path, capsys):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    package_plan = _make_plan(package_spec, repo_root)
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    render_output = _make_render_output(repo_root, package_spec.id)

    installer.run_install(
        ["--servers", package_spec.id, "--silent"],
        repo_root=repo_root,
        load_registry_fn=lambda _path: {package_spec.id: package_spec},
        resolve_selection_fn=lambda _selection, _registry: [package_spec],
        build_runtime_plan_fn=lambda _spec, _root: package_plan,
        run_runtime_plan_fn=lambda plan: plan,
        classify_runtime_readiness_fn=lambda _plan, user_home=None: ready_result,
        render_install_artifacts_fn=lambda *_args, **_kwargs: render_output,
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_run_install_verbose_flag_prints_per_server_statuses(tmp_path: Path, capsys):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    blocked_spec = _make_server_spec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )
    package_plan = _make_plan(package_spec, repo_root)
    blocked_plan = _make_plan(blocked_spec, repo_root)
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    blocked_result = ReadinessResult(server_id=blocked_spec.id, status="blocked", message="Blocked.")
    render_output = _make_render_output(repo_root, package_spec.id)

    installer.run_install(
        ["--servers", f"{package_spec.id},{blocked_spec.id}", "--verbose"],
        repo_root=repo_root,
        load_registry_fn=lambda _path: {package_spec.id: package_spec, blocked_spec.id: blocked_spec},
        resolve_selection_fn=lambda _selection, _registry: [package_spec, blocked_spec],
        build_runtime_plan_fn=lambda spec, _root: package_plan if spec.id == package_spec.id else blocked_plan,
        run_runtime_plan_fn=lambda plan: plan,
        classify_runtime_readiness_fn=(
            lambda plan, user_home=None: ready_result if plan.spec.id == package_spec.id else blocked_result
        ),
        render_install_artifacts_fn=lambda *_args, **_kwargs: render_output,
    )

    captured = capsys.readouterr()

    assert "- oci-api-mcp-server: ready - Ready." in captured.out
    assert "- dbtools-mcp-server: blocked - Blocked." in captured.out
    assert captured.err == ""


def test_run_install_debug_flag_prints_runtime_plan_details(tmp_path: Path, capsys):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    package_plan = _make_plan(package_spec, repo_root)
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    render_output = _make_render_output(repo_root, package_spec.id)

    installer.run_install(
        ["--servers", package_spec.id, "--debug"],
        repo_root=repo_root,
        load_registry_fn=lambda _path: {package_spec.id: package_spec},
        resolve_selection_fn=lambda _selection, _registry: [package_spec],
        build_runtime_plan_fn=lambda _spec, _root: package_plan,
        run_runtime_plan_fn=lambda plan: plan,
        classify_runtime_readiness_fn=lambda _plan, user_home=None: ready_result,
        render_install_artifacts_fn=lambda *_args, **_kwargs: render_output,
    )

    captured = capsys.readouterr()

    assert "Runtime details:" in captured.out
    assert str(package_plan.python_path) in captured.out
    assert str(package_plan.install_target) in captured.out
    assert captured.err == ""


def test_run_install_debug_and_verbose_flags_match_debug_output(tmp_path: Path, capsys):
    installer = _installer_module()
    repo_root = tmp_path / "repo"
    package_spec = _make_server_spec()
    package_plan = _make_plan(package_spec, repo_root)
    ready_result = ReadinessResult(server_id=package_spec.id, status="ready", message="Ready.")
    render_output = _make_render_output(repo_root, package_spec.id)

    result = installer.run_install(
        ["--servers", package_spec.id, "--verbose", "--debug"],
        repo_root=repo_root,
        load_registry_fn=lambda _path: {package_spec.id: package_spec},
        resolve_selection_fn=lambda _selection, _registry: [package_spec],
        build_runtime_plan_fn=lambda _spec, _root: package_plan,
        run_runtime_plan_fn=lambda plan: plan,
        classify_runtime_readiness_fn=lambda _plan, user_home=None: ready_result,
        render_install_artifacts_fn=lambda *_args, **_kwargs: render_output,
    )

    captured = capsys.readouterr()

    assert result.args.output_level == "debug"
    assert "Per-server results:" in captured.out
    assert "Runtime details:" in captured.out
    assert captured.err == ""


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
    assert "--silent" in result.stdout
    assert "--verbose" in result.stdout
    assert "--debug" in result.stdout


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
