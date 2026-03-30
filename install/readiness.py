from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from install.models import ReadinessResult, ServerSpec
from install.runtime_ops import RuntimePlan, build_runtime_plan


type PathExists = Callable[[Path], bool]


def classify_server_readiness(
    spec: ServerSpec,
    repo_root: str | Path,
    user_home: str | Path | None = None,
    path_exists: PathExists | None = None,
) -> ReadinessResult:
    return classify_runtime_readiness(
        build_runtime_plan(spec, repo_root),
        user_home=user_home,
        path_exists=path_exists,
    )


def classify_runtime_readiness(
    plan: RuntimePlan,
    user_home: str | Path | None = None,
    path_exists: PathExists | None = None,
) -> ReadinessResult:
    exists = path_exists or Path.exists

    if plan.spec.install_mode == "package":
        console_script = runtime_console_script_path(plan)
        checked_paths = (plan.python_path, console_script)
        missing_paths = tuple(path for path in checked_paths if not exists(path))
        if missing_paths:
            return ReadinessResult(
                server_id=plan.spec.id,
                status="failed",
                message="Required runtime artifacts are missing.",
                checked_paths=checked_paths,
                missing_paths=missing_paths,
            )
        return _classify_post_install_readiness(
            plan,
            checked_paths,
            "Runtime python and console script are available.",
            user_home,
            exists,
        )
    if plan.spec.install_mode != "script":
        raise ValueError(f"Unsupported install mode for '{plan.spec.id}': {plan.spec.install_mode}")

    entrypoint_path = plan.repo_root / plan.spec.entrypoint
    checked_paths = (plan.python_path, entrypoint_path)
    missing_paths = tuple(path for path in checked_paths if not exists(path))
    if missing_paths:
        return ReadinessResult(
            server_id=plan.spec.id,
            status="failed",
            message="Required runtime artifacts are missing.",
            checked_paths=checked_paths,
            missing_paths=missing_paths,
        )

    return _classify_post_install_readiness(
        plan,
        checked_paths,
        "Runtime python and entrypoint are available.",
        user_home,
        exists,
    )


def _classify_post_install_readiness(
    plan: RuntimePlan,
    checked_paths: tuple[Path, ...],
    ready_message: str,
    user_home: str | Path | None,
    exists: PathExists,
) -> ReadinessResult:
    if plan.spec.readiness_check == "basic":
        return ReadinessResult(
            server_id=plan.spec.id,
            status="ready",
            message=ready_message,
            checked_paths=checked_paths,
        )

    if plan.spec.readiness_check == "oracle_db_doc_index":
        index_path = oracle_db_doc_index_path(user_home)
        if not exists(index_path):
            return ReadinessResult(
                server_id=plan.spec.id,
                status="blocked",
                message="Oracle DB Doc index is missing.",
                checked_paths=checked_paths + (index_path,),
                missing_paths=(index_path,),
            )
        return ReadinessResult(
            server_id=plan.spec.id,
            status="ready",
            message=f"{ready_message.removesuffix('.')} and Oracle DB Doc index are available.",
            checked_paths=checked_paths + (index_path,),
        )

    raise ValueError(
        f"Unsupported readiness check for '{plan.spec.id}': {plan.spec.readiness_check}"
    )


def runtime_console_script_path(plan: RuntimePlan) -> Path:
    if sys.platform == "win32":
        return plan.venv_dir / "Scripts" / f"{plan.spec.entrypoint}.exe"
    return plan.venv_dir / "bin" / plan.spec.entrypoint


def oracle_db_doc_index_path(user_home: str | Path | None = None) -> Path:
    home = Path(user_home) if user_home is not None else Path.home()
    return home / ".oracle" / "oracle-db-doc-mcp-server" / "index.db"
