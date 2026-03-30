from __future__ import annotations

import re
import tomllib
from pathlib import Path

from install.models import ServerSpec


class RegistryError(ValueError):
    """Raised when installer registry metadata is invalid."""


REQUIRED_FIELDS = (
    "id",
    "display_name",
    "source_path",
    "install_mode",
    "launch_mode",
    "entrypoint",
)
ALLOWED_INSTALL_MODES = {"package", "script"}
ALLOWED_LAUNCH_MODES = {"console_script", "python_script"}
PYTHON_VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
CONSOLE_SCRIPT_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def load_registry(registry_path: str | Path) -> dict[str, ServerSpec]:
    path = Path(registry_path)
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"Registry file not found: {path}") from exc
    except OSError as exc:
        raise RegistryError(f"Failed to read registry '{path}': {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"Failed to parse registry '{path}': {exc}") from exc
    servers = payload.get("servers")
    if not isinstance(servers, dict):
        raise RegistryError("Registry must define a [servers] table.")

    registry: dict[str, ServerSpec] = {}
    for key, raw_entry in servers.items():
        if not isinstance(raw_entry, dict):
            raise RegistryError(f"Invalid entry for '{key}': expected a table.")
        spec = _build_server_spec(key, raw_entry)
        if spec.id in registry:
            raise RegistryError(f"Registry entry '{key}' reuses duplicate server id: {spec.id}")
        registry[spec.id] = spec
    return registry


def resolve_selection(selection: str, registry: dict[str, ServerSpec]) -> list[ServerSpec]:
    selection = selection.strip()
    if not selection:
        raise RegistryError("Selection must not be empty.")
    if selection == "all":
        specs = [
            spec
            for spec in registry.values()
            if _is_supported_python_server(spec)
        ]
        return sorted(specs, key=lambda spec: spec.id)

    resolved: list[ServerSpec] = []
    seen: set[str] = set()
    for server_id in [item.strip() for item in selection.split(",") if item.strip()]:
        if server_id in seen:
            continue
        if server_id not in registry:
            raise RegistryError(f"Unknown server id: {server_id}")
        seen.add(server_id)
        resolved.append(registry[server_id])
    return resolved


def _build_server_spec(key: str, raw_entry: dict[str, object]) -> ServerSpec:
    missing = [
        field_name
        for field_name in REQUIRED_FIELDS
        if not isinstance(raw_entry.get(field_name), str) or not raw_entry[field_name].strip()
    ]
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise RegistryError(f"Registry entry '{key}' is missing required fields: {missing_csv}")

    server_id = raw_entry["id"]
    if server_id == "all":
        raise RegistryError("Registry entry id 'all' is a reserved id.")
    if server_id != key:
        raise RegistryError(f"Registry entry key '{key}' must match id '{server_id}'.")

    launch_args = raw_entry.get("launch_args") or []
    env_hints = raw_entry.get("env_hints") or []
    if not isinstance(launch_args, list):
        raise RegistryError(f"Registry entry '{key}' launch_args must be a list.")
    if not isinstance(env_hints, list):
        raise RegistryError(f"Registry entry '{key}' env_hints must be a list.")
    if not all(isinstance(value, str) for value in launch_args):
        raise RegistryError(f"Registry entry '{key}' launch_args must contain only strings.")
    if not all(isinstance(value, str) for value in env_hints):
        raise RegistryError(f"Registry entry '{key}' env_hints must contain only strings.")

    install_mode = raw_entry["install_mode"]
    launch_mode = raw_entry["launch_mode"]
    entrypoint = raw_entry["entrypoint"]
    requirements_path = _opt_str(raw_entry.get("requirements_path"))
    if install_mode not in ALLOWED_INSTALL_MODES:
        raise RegistryError(f"Unsupported install_mode for '{key}': {install_mode}")
    if launch_mode not in ALLOWED_LAUNCH_MODES:
        raise RegistryError(f"Unsupported launch_mode for '{key}': {launch_mode}")
    if install_mode == "script":
        if launch_mode != "python_script":
            raise RegistryError(f"Script entry '{key}' must use launch_mode 'python_script'.")
        if not requirements_path:
            raise RegistryError(f"Script entry '{key}' must define requirements_path.")
    if install_mode == "package":
        if launch_mode != "console_script":
            raise RegistryError(f"Package entry '{key}' must use launch_mode 'console_script'.")
        if requirements_path:
            raise RegistryError(f"Package entry '{key}' must not define requirements_path.")
    _validate_entrypoint(key, install_mode, entrypoint)
    python_version = _validated_python_version(key, raw_entry.get("python_version"))

    return ServerSpec(
        id=server_id,
        display_name=raw_entry["display_name"],
        source_path=raw_entry["source_path"],
        install_mode=install_mode,
        launch_mode=launch_mode,
        entrypoint=entrypoint,
        launch_args=tuple(launch_args),
        python_version=python_version,
        requirements_path=requirements_path,
        readiness_check=_with_default(raw_entry.get("readiness_check"), "basic"),
        env_hints=tuple(env_hints),
        notes=_opt_str(raw_entry.get("notes")),
    )


def _is_supported_python_server(spec: ServerSpec) -> bool:
    if not spec.python_version:
        return False
    if spec.install_mode not in ALLOWED_INSTALL_MODES:
        return False
    if spec.launch_mode not in ALLOWED_LAUNCH_MODES:
        return False
    return True


def _opt_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _validate_entrypoint(key: str, install_mode: str, entrypoint: str) -> None:
    if install_mode == "package":
        if not CONSOLE_SCRIPT_PATTERN.fullmatch(entrypoint) or entrypoint.endswith(".py"):
            raise RegistryError(
                f"Package entry '{key}' must define a console-script-like entrypoint."
            )
        return

    if entrypoint.endswith(".py") and not any(char.isspace() for char in entrypoint):
        return
    raise RegistryError(f"Script entry '{key}' must define a path-like .py entrypoint.")


def _validated_python_version(key: str, value: object) -> str:
    if value in (None, ""):
        return "3.13"
    if not isinstance(value, str) or not PYTHON_VERSION_PATTERN.fullmatch(value):
        raise RegistryError(
            f"Registry entry '{key}' python_version must be an exact X.Y or X.Y.Z string."
        )
    return value


def _with_default(value: object, default: str) -> str:
    if value in (None, ""):
        return default
    return str(value)
