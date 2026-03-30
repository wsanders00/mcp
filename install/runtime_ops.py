from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from install.models import ServerSpec


type CommandRunner = Callable[[list[str], Path], None]
type DirectoryCreator = Callable[[Path], None]


@dataclass(frozen=True)
class RuntimePlan:
    spec: ServerSpec
    repo_root: Path
    runtime_root: Path
    server_runtime_dir: Path
    venv_dir: Path
    python_path: Path
    install_target: Path


def build_runtime_plan(spec: ServerSpec, repo_root: str | Path) -> RuntimePlan:
    root = Path(repo_root)
    runtime_root = root / "install" / "runtime"
    server_runtime_dir = runtime_root / spec.id
    venv_dir = server_runtime_dir / "venv"
    python_path = venv_dir / _python_relative_path()
    install_target = _resolve_install_target(spec, root)

    return RuntimePlan(
        spec=spec,
        repo_root=root,
        runtime_root=runtime_root,
        server_runtime_dir=server_runtime_dir,
        venv_dir=venv_dir,
        python_path=python_path,
        install_target=install_target,
    )


def run_runtime_plan(
    plan: RuntimePlan,
    command_runner: CommandRunner | None = None,
    ensure_dir: DirectoryCreator | None = None,
    uv_executable: str = "uv",
) -> RuntimePlan:
    runner = command_runner or _run_command
    create_dir = ensure_dir or _ensure_directory
    create_dir(plan.server_runtime_dir)

    runner(
        [
            uv_executable,
            "venv",
            str(plan.venv_dir),
            "--python",
            plan.spec.python_version,
            "--allow-existing",
        ],
        plan.repo_root,
    )
    runner(_build_install_command(plan, uv_executable), plan.repo_root)
    return plan


def _resolve_install_target(spec: ServerSpec, repo_root: Path) -> Path:
    if spec.install_mode == "package":
        return repo_root / spec.source_path
    if spec.install_mode == "script":
        if not spec.requirements_path:
            raise ValueError(f"Script server '{spec.id}' requires a requirements_path.")
        return repo_root / spec.requirements_path
    raise ValueError(f"Unsupported install mode for '{spec.id}': {spec.install_mode}")


def _build_install_command(plan: RuntimePlan, uv_executable: str) -> list[str]:
    command = [uv_executable, "pip", "install", "--python", str(plan.python_path)]
    if plan.spec.install_mode == "package":
        command.append(str(plan.install_target))
        return command
    if plan.spec.install_mode == "script":
        command.extend(["-r", str(plan.install_target)])
        return command
    raise ValueError(f"Unsupported install mode for '{plan.spec.id}': {plan.spec.install_mode}")


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _run_command(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _python_relative_path() -> Path:
    if sys.platform == "win32":
        return Path("Scripts") / "python.exe"
    return Path("bin") / "python"
