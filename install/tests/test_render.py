from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess

from install.models import ReadinessResult, ServerSpec
from install.runtime_ops import build_runtime_plan


def _render_module():
    return importlib.import_module("install.render")


def _template_root() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"


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


def test_render_install_artifacts_writes_ready_wrappers_examples_and_reports(tmp_path: Path):
    render = _render_module()
    package_spec = _make_server_spec()
    script_spec = _make_server_spec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        launch_args=("mcp",),
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
    )
    failed_spec = _make_server_spec(
        id="oci-logging-mcp-server",
        display_name="OCI Logging MCP Server",
        source_path="src/oci-logging-mcp-server",
        entrypoint="oracle.oci-logging-mcp-server",
    )

    package_plan = build_runtime_plan(package_spec, tmp_path)
    script_plan = build_runtime_plan(script_spec, tmp_path)
    failed_plan = build_runtime_plan(failed_spec, tmp_path)

    stale_wrapper = tmp_path / "install" / "generated" / "wrappers" / "stale.sh"
    stale_wrapper.parent.mkdir(parents=True, exist_ok=True)
    stale_wrapper.write_text("stale\n", encoding="utf-8")

    readiness_results = [
        ReadinessResult(server_id=package_spec.id, status="ready", message="Runtime ready."),
        ReadinessResult(server_id=script_spec.id, status="ready", message="Runtime ready."),
        ReadinessResult(server_id=failed_spec.id, status="failed", message="Console script missing."),
    ]

    rendered = render.render_install_artifacts(
        [package_plan, script_plan, failed_plan],
        readiness_results,
        tmp_path,
        template_root=_template_root(),
        force=True,
    )

    assert not stale_wrapper.exists()
    assert [path.name for path in rendered.wrapper_paths] == [
        "oci-api-mcp-server.sh",
        "oracle-db-doc-mcp-server.sh",
    ]
    assert rendered.codex_example_path == tmp_path / "install" / "generated" / "examples" / "codex.example.json"
    assert rendered.vscode_example_path == tmp_path / "install" / "generated" / "examples" / "vscode.mcp.json"
    assert rendered.report_markdown_path == tmp_path / "install" / "generated" / "reports" / "install-report.md"
    assert rendered.report_json_path == tmp_path / "install" / "generated" / "reports" / "install-report.json"

    package_wrapper = rendered.wrapper_paths[0]
    package_text = package_wrapper.read_text(encoding="utf-8")
    assert package_wrapper.stat().st_mode & 0o111
    assert str(package_plan.venv_dir / "bin" / package_spec.entrypoint) in package_text
    assert '"$@"' in package_text
    assert "$$@" not in package_text

    package_console = package_plan.venv_dir / "bin" / package_spec.entrypoint
    captured_args = tmp_path / "captured-args.txt"
    package_console.parent.mkdir(parents=True, exist_ok=True)
    package_console.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\n' \"$@\" > "
        f"{captured_args}\n",
        encoding="utf-8",
    )
    package_console.chmod(0o755)
    subprocess.run([str(package_wrapper), "alpha", "beta"], check=True)
    assert captured_args.read_text(encoding="utf-8").splitlines() == ["alpha", "beta"]

    script_wrapper = rendered.wrapper_paths[1]
    script_text = script_wrapper.read_text(encoding="utf-8")
    assert script_wrapper.stat().st_mode & 0o111
    assert str(script_plan.python_path) in script_text
    assert str(tmp_path / script_spec.entrypoint) in script_text
    assert "mcp" in script_text

    codex_example = json.loads(rendered.codex_example_path.read_text(encoding="utf-8"))
    assert set(codex_example["mcpServers"]) == {
        package_spec.id,
        script_spec.id,
    }
    assert failed_spec.id not in codex_example["mcpServers"]
    assert codex_example["mcpServers"][package_spec.id]["command"] == str(package_wrapper)

    vscode_example = json.loads(rendered.vscode_example_path.read_text(encoding="utf-8"))
    assert set(vscode_example["servers"]) == {
        package_spec.id,
        script_spec.id,
    }
    assert failed_spec.id not in vscode_example["servers"]
    assert vscode_example["servers"][script_spec.id]["command"] == str(script_wrapper)

    report = json.loads(rendered.report_json_path.read_text(encoding="utf-8"))
    assert [item["server_id"] for item in report["servers"]] == [
        package_spec.id,
        script_spec.id,
        failed_spec.id,
    ]
    assert [item["status"] for item in report["servers"]] == ["ready", "ready", "failed"]
    assert rendered.report_markdown_path.parent == tmp_path / "install" / "generated" / "reports"


def test_render_install_artifacts_reconciles_outputs_on_non_force_rerun(tmp_path: Path):
    render = _render_module()
    ready_spec = _make_server_spec()
    blocked_spec = _make_server_spec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )

    ready_plan = build_runtime_plan(ready_spec, tmp_path)
    blocked_plan = build_runtime_plan(blocked_spec, tmp_path)

    first_render = render.render_install_artifacts(
        [ready_plan, blocked_plan],
        [
            ReadinessResult(server_id=ready_spec.id, status="ready", message="Ready."),
            ReadinessResult(server_id=blocked_spec.id, status="blocked", message="Docs index missing."),
        ],
        tmp_path,
        template_root=_template_root(),
    )

    ready_wrapper = first_render.wrapper_paths[0]
    assert ready_wrapper.exists()

    second_render = render.render_install_artifacts(
        [ready_plan, blocked_plan],
        [
            ReadinessResult(server_id=ready_spec.id, status="failed", message="Wrapper missing."),
            ReadinessResult(server_id=blocked_spec.id, status="blocked", message="Docs index missing."),
        ],
        tmp_path,
        template_root=_template_root(),
    )

    assert ready_wrapper.exists() is False
    assert second_render.wrapper_paths == ()

    codex_example = json.loads(second_render.codex_example_path.read_text(encoding="utf-8"))
    vscode_example = json.loads(second_render.vscode_example_path.read_text(encoding="utf-8"))

    assert codex_example["mcpServers"] == {}
    assert vscode_example["servers"] == {}
