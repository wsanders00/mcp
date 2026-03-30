from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ServerSpec:
    id: str
    display_name: str
    source_path: str
    install_mode: str
    launch_mode: str
    entrypoint: str
    launch_args: tuple[str, ...] = field(default_factory=tuple)
    python_version: str = "3.13"
    requirements_path: str | None = None
    readiness_check: str = "basic"
    env_hints: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


@dataclass(frozen=True)
class ReadinessResult:
    server_id: str
    status: str
    message: str
    checked_paths: tuple[Path, ...] = field(default_factory=tuple)
    missing_paths: tuple[Path, ...] = field(default_factory=tuple)
