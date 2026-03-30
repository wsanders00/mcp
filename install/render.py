from __future__ import annotations

import json
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

from install.models import ReadinessResult
from install.readiness import runtime_console_script_path
from install.runtime_ops import RuntimePlan


@dataclass(frozen=True)
class RenderResult:
    generated_root: Path
    wrapper_paths: tuple[Path, ...]
    codex_example_path: Path
    vscode_example_path: Path
    report_markdown_path: Path
    report_json_path: Path


def render_install_artifacts(
    runtime_plans: list[RuntimePlan] | tuple[RuntimePlan, ...],
    readiness_results: list[ReadinessResult] | tuple[ReadinessResult, ...],
    repo_root: str | Path,
    *,
    template_root: str | Path | None = None,
    generated_root: str | Path | None = None,
    force: bool = False,
) -> RenderResult:
    if sys.platform == "win32":
        raise RuntimeError("Installer artifact rendering currently targets Unix only.")
    if len(runtime_plans) != len(readiness_results):
        raise ValueError("Runtime plans and readiness results must have matching lengths.")

    root = Path(repo_root)
    templates_dir = (
        Path(template_root) if template_root is not None else Path(__file__).resolve().with_name("templates")
    )
    output_root = Path(generated_root) if generated_root is not None else root / "install" / "generated"
    wrappers_dir = output_root / "wrappers"
    examples_dir = output_root / "examples"
    reports_dir = output_root / "reports"
    codex_example_path = examples_dir / "codex.example.json"
    vscode_example_path = examples_dir / "vscode.mcp.json"
    report_markdown_path = reports_dir / "install-report.md"
    report_json_path = reports_dir / "install-report.json"

    if force and output_root.exists():
        shutil.rmtree(output_root)

    _reset_generated_subtree(wrappers_dir)
    _reset_generated_subtree(examples_dir)
    _reset_generated_subtree(reports_dir)
    _remove_legacy_generated_files(output_root)

    readiness_by_id = {result.server_id: result for result in readiness_results}
    missing_result_ids = [plan.spec.id for plan in runtime_plans if plan.spec.id not in readiness_by_id]
    if missing_result_ids:
        missing_csv = ", ".join(missing_result_ids)
        raise ValueError(f"Missing readiness results for: {missing_csv}")

    wrapper_paths: list[Path] = []
    wrapper_by_id: dict[str, Path] = {}
    for plan in runtime_plans:
        result = readiness_by_id[plan.spec.id]
        if result.status != "ready":
            continue
        wrapper_path = wrappers_dir / f"{plan.spec.id}.sh"
        wrapper_text = _render_template(
            templates_dir / "server-wrapper.sh.tmpl",
            command_line=_wrapper_command_line(plan),
            repo_root=shlex.quote(str(root)),
            server_id=plan.spec.id,
        )
        _write_text(wrapper_path, wrapper_text)
        wrapper_path.chmod(0o755)
        wrapper_paths.append(wrapper_path)
        wrapper_by_id[plan.spec.id] = wrapper_path

    codex_payload = {
        "mcpServers": {
            plan.spec.id: {
                "command": str(wrapper_by_id[plan.spec.id]),
                "args": [],
            }
            for plan in runtime_plans
            if plan.spec.id in wrapper_by_id
        }
    }
    vscode_payload = {
        "servers": {
            plan.spec.id: {
                "type": "stdio",
                "command": str(wrapper_by_id[plan.spec.id]),
                "args": [],
            }
            for plan in runtime_plans
            if plan.spec.id in wrapper_by_id
        }
    }

    _write_text(
        codex_example_path,
        _render_template(
            templates_dir / "codex.example.json.tmpl",
            servers_json=json.dumps(codex_payload["mcpServers"], indent=2),
        ),
    )
    _write_text(
        vscode_example_path,
        _render_template(
            templates_dir / "vscode.mcp.json.tmpl",
            servers_json=json.dumps(vscode_payload["servers"], indent=2),
        ),
    )

    ready_count = sum(1 for result in readiness_results if result.status == "ready")
    blocked_count = sum(1 for result in readiness_results if result.status == "blocked")
    failed_count = sum(1 for result in readiness_results if result.status == "failed")
    server_rows = "\n".join(_report_row(result) for result in readiness_results) or "- none"
    _write_text(
        report_markdown_path,
        _render_template(
            templates_dir / "install-report.md.tmpl",
            blocked_count=str(blocked_count),
            codex_example_path=str(codex_example_path),
            failed_count=str(failed_count),
            generated_root=str(output_root),
            ready_count=str(ready_count),
            report_json_path=str(report_json_path),
            server_rows=server_rows,
            vscode_example_path=str(vscode_example_path),
        ),
    )

    report_payload = {
        "generated_root": str(output_root),
        "artifacts": {
            "codex_example_path": str(codex_example_path),
            "vscode_example_path": str(vscode_example_path),
            "report_markdown_path": str(report_markdown_path),
            "wrapper_paths": {
                plan.spec.id: str(wrapper_by_id[plan.spec.id])
                for plan in runtime_plans
                if plan.spec.id in wrapper_by_id
            },
        },
        "servers": [
            {
                "server_id": result.server_id,
                "status": result.status,
                "message": result.message,
                "checked_paths": [str(path) for path in result.checked_paths],
                "missing_paths": [str(path) for path in result.missing_paths],
            }
            for result in readiness_results
        ],
    }
    _write_text(report_json_path, json.dumps(report_payload, indent=2) + "\n")

    return RenderResult(
        generated_root=output_root,
        wrapper_paths=tuple(wrapper_paths),
        codex_example_path=codex_example_path,
        vscode_example_path=vscode_example_path,
        report_markdown_path=report_markdown_path,
        report_json_path=report_json_path,
    )


def _render_template(template_path: Path, **context: str) -> str:
    return Template(template_path.read_text(encoding="utf-8")).substitute(**context)


def _report_row(result: ReadinessResult) -> str:
    missing_suffix = ""
    if result.missing_paths:
        missing_csv = ", ".join(str(path) for path in result.missing_paths)
        missing_suffix = f" (missing: {missing_csv})"
    return f"- {result.server_id}: {result.status} - {result.message}{missing_suffix}"


def _wrapper_command_line(plan: RuntimePlan) -> str:
    if plan.spec.install_mode == "package":
        command = [str(runtime_console_script_path(plan)), *plan.spec.launch_args]
        return shlex.join(command)
    if plan.spec.install_mode == "script":
        command = [
            str(plan.python_path),
            str(plan.repo_root / plan.spec.entrypoint),
            *plan.spec.launch_args,
        ]
        return shlex.join(command)
    raise ValueError(f"Unsupported install mode for '{plan.spec.id}': {plan.spec.install_mode}")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")


def _reset_generated_subtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_legacy_generated_files(output_root: Path) -> None:
    for legacy_name in ("codex.example.json", "vscode.mcp.json"):
        legacy_path = output_root / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()
