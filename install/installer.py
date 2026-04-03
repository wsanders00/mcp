from __future__ import annotations

if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path

    repo_root = str(_Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

import argparse
from dataclasses import dataclass
from collections.abc import Callable, Iterable
from pathlib import Path

from install.models import ReadinessResult, ServerSpec
from install.readiness import classify_runtime_readiness
from install.registry import load_registry, resolve_selection
from install.render import RenderResult, render_install_artifacts
from install.runtime_ops import RuntimePlan, build_runtime_plan, run_runtime_plan


PROMPT = "Select server(s) to install (comma-separated or 'all'): "
DEFAULT_OUTPUT_LEVEL = "normal"


@dataclass(frozen=True)
class InstallRunResult:
    args: argparse.Namespace
    selection: str
    selected_server_ids: tuple[str, ...]
    runtime_plans: tuple[object, ...]
    readiness_results: tuple[ReadinessResult, ...]
    render_output: object


class InstallArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args=args, namespace=namespace)
        parsed.output_level = _resolve_output_level(parsed)
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = InstallArgumentParser(description="Local MCP installer")
    parser.add_argument(
        "--servers",
        help="Comma-separated server ids to install, or 'all' for every supported server.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove and regenerate install/generated/ before writing new artifacts.",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress installer output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-server installer results.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print per-server results plus runtime path details. Implies --verbose.",
    )
    return parser


def choose_selection(
    source: argparse.Namespace | str | Iterable[str] | None,
    input_fn: Callable[[str], str] | None = None,
) -> str:
    raw_selection = _coerce_selection(source)
    if raw_selection is None:
        prompt_input = input if input_fn is None else input_fn
        raw_selection = prompt_input(PROMPT)
    normalized = _normalize_selection(raw_selection)
    if not normalized:
        raise ValueError("Selection must not be empty.")
    return normalized


def _coerce_selection(source: argparse.Namespace | str | Iterable[str] | None) -> str | None:
    if source is None:
        return None
    if isinstance(source, argparse.Namespace):
        namespace_value = getattr(source, "servers", None)
        if namespace_value is None:
            return None
        return _coerce_selection(namespace_value)
    if isinstance(source, str):
        return source
    if isinstance(source, Iterable):
        parts = list(source)
        if not all(isinstance(part, str) for part in parts):
            raise TypeError("Selection iterables must contain only strings.")
        return ",".join(parts)
    raise TypeError("Selection must be an argparse.Namespace, string, iterable of strings, or None.")


def _resolve_output_level(args: argparse.Namespace) -> str:
    if getattr(args, "silent", False):
        return "silent"
    if getattr(args, "debug", False):
        return "debug"
    if getattr(args, "verbose", False):
        return "verbose"
    return DEFAULT_OUTPUT_LEVEL


def _normalize_selection(selection: str) -> str:
    if selection.strip().casefold() == "all":
        return "all"

    server_ids = [item.strip() for item in selection.split(",") if item.strip()]
    return ",".join(server_ids)


def run_install(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    repo_root: str | Path | None = None,
    registry_path: str | Path | None = None,
    input_fn: Callable[[str], str] | None = None,
    load_registry_fn: Callable[[str | Path], dict[str, ServerSpec]] = load_registry,
    resolve_selection_fn: Callable[[str, dict[str, ServerSpec]], list[ServerSpec]] = resolve_selection,
    build_runtime_plan_fn: Callable[[ServerSpec, str | Path], RuntimePlan | object] = build_runtime_plan,
    run_runtime_plan_fn: Callable[[RuntimePlan | object], RuntimePlan | object] = run_runtime_plan,
    classify_runtime_readiness_fn: Callable[..., ReadinessResult] = classify_runtime_readiness,
    render_install_artifacts_fn: Callable[..., RenderResult | object] = render_install_artifacts,
    user_home: str | Path | None = None,
) -> InstallRunResult:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    selection = choose_selection(args, input_fn=input_fn)
    root = _resolve_repo_root(repo_root)
    registry_file = Path(registry_path) if registry_path is not None else root / "install" / "servers.toml"

    registry = load_registry_fn(registry_file)
    specs = tuple(resolve_selection_fn(selection, registry))
    built_runtime_plans = tuple(build_runtime_plan_fn(spec, root) for spec in specs)
    runtime_plans: list[RuntimePlan | object] = []
    readiness_results: list[ReadinessResult] = []
    for plan in built_runtime_plans:
        try:
            runtime_plan = run_runtime_plan_fn(plan)
        except Exception as exc:
            runtime_plans.append(plan)
            readiness_results.append(_runtime_failure_result(plan, exc))
            continue

        runtime_plans.append(runtime_plan)
        readiness_results.append(classify_runtime_readiness_fn(runtime_plan, user_home=user_home))

    runtime_plans_tuple = tuple(runtime_plans)
    readiness_results_tuple = tuple(readiness_results)
    render_output = render_install_artifacts_fn(
        runtime_plans_tuple,
        readiness_results_tuple,
        root,
        force=args.force,
    )

    _emit_install_output(
        output_level=args.output_level,
        selection=tuple(spec.id for spec in specs),
        runtime_plans=runtime_plans_tuple,
        readiness_results=readiness_results_tuple,
        render_output=render_output,
    )

    return InstallRunResult(
        args=args,
        selection=selection,
        selected_server_ids=tuple(spec.id for spec in specs),
        runtime_plans=runtime_plans_tuple,
        readiness_results=readiness_results_tuple,
        render_output=render_output,
    )


def main(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    repo_root: str | Path | None = None,
    registry_path: str | Path | None = None,
    input_fn: Callable[[str], str] | None = None,
    load_registry_fn: Callable[[str | Path], dict[str, ServerSpec]] = load_registry,
    resolve_selection_fn: Callable[[str, dict[str, ServerSpec]], list[ServerSpec]] = resolve_selection,
    build_runtime_plan_fn: Callable[[ServerSpec, str | Path], RuntimePlan | object] = build_runtime_plan,
    run_runtime_plan_fn: Callable[[RuntimePlan | object], RuntimePlan | object] = run_runtime_plan,
    classify_runtime_readiness_fn: Callable[..., ReadinessResult] = classify_runtime_readiness,
    render_install_artifacts_fn: Callable[..., RenderResult | object] = render_install_artifacts,
    user_home: str | Path | None = None,
) -> InstallRunResult:
    return run_install(
        argv,
        repo_root=repo_root,
        registry_path=registry_path,
        input_fn=input_fn,
        load_registry_fn=load_registry_fn,
        resolve_selection_fn=resolve_selection_fn,
        build_runtime_plan_fn=build_runtime_plan_fn,
        run_runtime_plan_fn=run_runtime_plan_fn,
        classify_runtime_readiness_fn=classify_runtime_readiness_fn,
        render_install_artifacts_fn=render_install_artifacts_fn,
        user_home=user_home,
    )


def _resolve_repo_root(repo_root: str | Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    return Path(__file__).resolve().parents[1]


def _runtime_failure_result(plan: RuntimePlan | object, exc: Exception) -> ReadinessResult:
    checked_paths = tuple(
        path
        for path in (
            getattr(plan, "venv_dir", None),
            getattr(plan, "python_path", None),
            getattr(plan, "install_target", None),
        )
        if isinstance(path, Path)
    )
    return ReadinessResult(
        server_id=plan.spec.id,
        status="failed",
        message=f"Runtime provisioning failed: {exc}",
        checked_paths=checked_paths,
    )


def _emit_install_output(
    *,
    output_level: str,
    selection: tuple[str, ...],
    runtime_plans: tuple[RuntimePlan | object, ...],
    readiness_results: tuple[ReadinessResult, ...],
    render_output: object,
) -> None:
    if output_level == "silent":
        return

    lines = _summary_lines(selection, readiness_results, render_output)
    if output_level in {"verbose", "debug"}:
        lines.extend(_server_result_lines(readiness_results))
    if output_level == "debug":
        lines.extend(_runtime_debug_lines(runtime_plans))

    for line in lines:
        print(line)


def _summary_lines(
    selection: tuple[str, ...],
    readiness_results: tuple[ReadinessResult, ...],
    render_output: object,
) -> list[str]:
    ready_count, blocked_count, failed_count = _status_counts(readiness_results)
    lines = [
        f"Selected servers: {', '.join(selection)}",
        f"Ready: {ready_count}  Blocked: {blocked_count}  Failed: {failed_count}",
    ]

    for label, attr_name in (
        ("Generated root", "generated_root"),
        ("Codex example", "codex_example_path"),
        ("VS Code example", "vscode_example_path"),
        ("Report", "report_markdown_path"),
    ):
        artifact_path = getattr(render_output, attr_name, None)
        if artifact_path is not None:
            lines.append(f"{label}: {artifact_path}")

    return lines


def _server_result_lines(readiness_results: tuple[ReadinessResult, ...]) -> list[str]:
    if not readiness_results:
        return []

    return [
        "Per-server results:",
        *[
            f"- {result.server_id}: {result.status} - {result.message}"
            + _missing_paths_suffix(result)
            for result in readiness_results
        ],
    ]


def _missing_paths_suffix(result: ReadinessResult) -> str:
    if not result.missing_paths:
        return ""
    missing_csv = ", ".join(str(path) for path in result.missing_paths)
    return f" (missing: {missing_csv})"


def _runtime_debug_lines(runtime_plans: tuple[RuntimePlan | object, ...]) -> list[str]:
    if not runtime_plans:
        return []

    lines = ["Runtime details:"]
    for plan in runtime_plans:
        lines.append(f"- {plan.spec.id}")
        for label, attr_name in (
            ("runtime_dir", "server_runtime_dir"),
            ("venv_dir", "venv_dir"),
            ("python_path", "python_path"),
            ("install_target", "install_target"),
        ):
            value = getattr(plan, attr_name, None)
            if value is not None:
                lines.append(f"  {label}: {value}")
    return lines


def _status_counts(readiness_results: tuple[ReadinessResult, ...]) -> tuple[int, int, int]:
    return (
        sum(1 for result in readiness_results if result.status == "ready"),
        sum(1 for result in readiness_results if result.status == "blocked"),
        sum(1 for result in readiness_results if result.status == "failed"),
    )


if __name__ == "__main__":
    main()
