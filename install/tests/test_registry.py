from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from install.registry import RegistryError, load_registry, resolve_selection


def _seeded_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "install" / "servers.toml"


def test_resolve_all_returns_supported_python_server_ids_only(write_registry):
    registry_path = write_registry(
        """
        [servers.oci-api-mcp-server]
        id = "oci-api-mcp-server"
        display_name = "OCI API MCP Server"
        source_path = "src/oci-api-mcp-server"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "oracle.oci-api-mcp-server"

        [servers.oracle-db-doc-mcp-server]
        id = "oracle-db-doc-mcp-server"
        display_name = "Oracle DB Doc MCP Server"
        source_path = "src/oracle-db-doc-mcp-server"
        install_mode = "script"
        launch_mode = "python_script"
        entrypoint = "src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py"
        launch_args = ["mcp"]
        python_version = "3.13"
        requirements_path = "src/oracle-db-doc-mcp-server/requirements.txt"

        """
    )

    registry = load_registry(registry_path)
    resolved = resolve_selection("all", registry)

    assert [spec.id for spec in resolved] == [
        "oci-api-mcp-server",
        "oracle-db-doc-mcp-server",
    ]
    assert resolved[1].launch_args == ("mcp",)


def test_registry_rejects_entry_without_launch_metadata(write_registry):
    registry_path = write_registry(
        """
        [servers.bad-server]
        id = "bad-server"
        display_name = "Bad Server"
        source_path = "src/bad-server"
        install_mode = "package"
        launch_mode = "console_script"
        """
    )

    with pytest.raises(RegistryError, match="entrypoint"):
        load_registry(registry_path)


def test_registry_assigns_plan_defaults(write_registry):
    registry_path = write_registry(
        """
        [servers.defaulted]
        id = "defaulted"
        display_name = "Defaulted"
        source_path = "src/defaulted"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "defaulted-script"
        """
    )

    registry = load_registry(registry_path)
    spec = registry["defaulted"]
    assert spec.python_version == "3.13"
    assert spec.readiness_check == "basic"


def test_registry_rejects_key_id_mismatch(write_registry):
    registry_path = write_registry(
        """
        [servers.not-the-id]
        id = "actual-id"
        display_name = "Mismatched"
        source_path = "src/actual-id"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "actual-id"
        """
    )

    with pytest.raises(RegistryError, match="must match id"):
        load_registry(registry_path)


def test_registry_rejects_duplicate_server_ids(write_registry):
    registry_path = write_registry(
        """
        [servers.first]
        id = "dup"
        display_name = "First"
        source_path = "src/first"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "first"

        [servers.second]
        id = "dup"
        display_name = "Second"
        source_path = "src/second"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "second"
        """
    )

    with pytest.raises(RegistryError, match="must match id|duplicate server id"):
        load_registry(registry_path)


def test_registry_rejects_reserved_all_id(write_registry):
    registry_path = write_registry(
        """
        [servers.all]
        id = "all"
        display_name = "All"
        source_path = "src/all"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "all-server"
        """
    )

    with pytest.raises(RegistryError, match="reserved id"):
        load_registry(registry_path)


@pytest.mark.parametrize(
    ("field_name", "replacement_line"),
    [
        ("id", 'id = "   "'),
        ("display_name", 'display_name = "   "'),
        ("source_path", 'source_path = "   "'),
        ("install_mode", 'install_mode = "   "'),
        ("launch_mode", 'launch_mode = "   "'),
        ("entrypoint", 'entrypoint = "   "'),
    ],
)
def test_registry_rejects_blank_required_fields(write_registry, field_name, replacement_line):
    lines = {
        "id": 'id = "blank-server"',
        "display_name": 'display_name = "Blank Server"',
        "source_path": 'source_path = "src/blank-server"',
        "install_mode": 'install_mode = "package"',
        "launch_mode": 'launch_mode = "console_script"',
        "entrypoint": 'entrypoint = "blank-server"',
    }
    lines[field_name] = replacement_line
    registry_path = write_registry(
        f"""
        [servers.blank-server]
        {lines["id"]}
        {lines["display_name"]}
        {lines["source_path"]}
        {lines["install_mode"]}
        {lines["launch_mode"]}
        {lines["entrypoint"]}
        """
    )

    with pytest.raises(RegistryError, match=field_name):
        load_registry(registry_path)


@pytest.mark.parametrize("python_version", [">=3.13", "3", "3.13b1", "3.13.0.1", " 3.13 "])
def test_registry_rejects_invalid_python_version_format(write_registry, python_version):
    registry_path = write_registry(
        f"""
        [servers.bad-version]
        id = "bad-version"
        display_name = "Bad Version"
        source_path = "src/bad-version"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "bad-version"
        python_version = "{python_version}"
        """
    )

    with pytest.raises(RegistryError, match="python_version"):
        load_registry(registry_path)


def test_registry_accepts_patch_python_version(write_registry):
    registry_path = write_registry(
        """
        [servers.patch-version]
        id = "patch-version"
        display_name = "Patch Version"
        source_path = "src/patch-version"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "patch-version"
        python_version = "3.13.1"
        """
    )

    registry = load_registry(registry_path)

    assert registry["patch-version"].python_version == "3.13.1"


def test_registry_rejects_package_entrypoint_that_looks_like_a_path(write_registry):
    registry_path = write_registry(
        """
        [servers.package-server]
        id = "package-server"
        display_name = "Package Server"
        source_path = "src/package-server"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "src/package-server/server.py"
        """
    )

    with pytest.raises(RegistryError, match="console-script-like"):
        load_registry(registry_path)


def test_registry_rejects_script_entrypoint_that_is_not_a_python_path(write_registry):
    registry_path = write_registry(
        """
        [servers.script-server]
        id = "script-server"
        display_name = "Script Server"
        source_path = "src/script-server"
        install_mode = "script"
        launch_mode = "python_script"
        entrypoint = "script-server"
        requirements_path = "src/script-server/requirements.txt"
        """
    )

    with pytest.raises(RegistryError, match="path-like .py"):
        load_registry(registry_path)


@pytest.mark.parametrize(
    ("field_name", "field_line"),
    [
        ("launch_args", "launch_args = [1]"),
        ("env_hints", "env_hints = [true]"),
    ],
)
def test_registry_rejects_non_string_list_members(write_registry, field_name, field_line):
    registry_path = write_registry(
        f"""
        [servers.bad-list-values]
        id = "bad-list-values"
        display_name = "Bad List Values"
        source_path = "src/bad-list-values"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "bad-list-values"
        {field_line}
        """
    )

    with pytest.raises(RegistryError, match=field_name):
        load_registry(registry_path)


def test_resolve_selection_preserves_explicit_order_and_deduplicates():
    registry = load_registry(_seeded_registry_path())

    resolved = resolve_selection(
        "oracle-db-doc-mcp-server,dbtools-mcp-server,oracle-db-doc-mcp-server",
        registry,
    )

    assert [spec.id for spec in resolved] == [
        "oracle-db-doc-mcp-server",
        "dbtools-mcp-server",
    ]


def test_resolve_selection_rejects_empty_value():
    registry = load_registry(_seeded_registry_path())

    with pytest.raises(RegistryError, match="empty"):
        resolve_selection("   ", registry)


def test_seeded_registry_uses_console_script_metadata_for_package_servers():
    registry = load_registry(_seeded_registry_path())
    mysql = registry["mysql-mcp-server"]
    pricing = registry["oci-pricing-mcp-server"]
    api = registry["oci-api-mcp-server"]
    dbtools = registry["dbtools-mcp-server"]
    db_doc = registry["oracle-db-doc-mcp-server"]

    assert len(registry) == 25
    assert mysql.python_version == "3.12"
    assert pricing.install_mode == "package"
    assert pricing.launch_mode == "console_script"
    assert pricing.entrypoint == "oci-pricing-mcp"
    assert pricing.python_version == "3.11"
    assert api.install_mode == "package"
    assert api.launch_mode == "console_script"
    assert dbtools.install_mode == "script"
    assert dbtools.launch_mode == "python_script"
    assert dbtools.requirements_path == "src/dbtools-mcp-server/requirements.txt"
    assert db_doc.install_mode == "script"
    assert db_doc.launch_mode == "python_script"
    assert db_doc.launch_args == ("mcp",)
    assert db_doc.readiness_check == "oracle_db_doc_index"


def test_seeded_registry_paths_and_entrypoints_match_repo_sources():
    repo_root = Path(__file__).resolve().parents[2]
    registry = load_registry(_seeded_registry_path())

    for spec in registry.values():
        source_dir = repo_root / spec.source_path
        assert source_dir.exists(), spec.id

        if spec.install_mode == "package":
            pyproject = tomllib.loads((source_dir / "pyproject.toml").read_text(encoding="utf-8"))
            scripts = pyproject["project"].get("scripts", {})
            requires_python = pyproject["project"].get("requires-python")

            assert spec.entrypoint in scripts, spec.id
            assert spec.python_version == requires_python.removeprefix(">="), spec.id
        else:
            assert (repo_root / spec.entrypoint).exists(), spec.id
            assert spec.requirements_path is not None, spec.id
            assert (repo_root / spec.requirements_path).exists(), spec.id


def test_registry_wraps_toml_parse_errors(write_registry):
    registry_path = write_registry(
        """
        [servers.bad
        id = "bad"
        """
    )

    with pytest.raises(RegistryError, match="Failed to parse"):
        load_registry(registry_path)


def test_registry_rejects_unsupported_modes(write_registry):
    registry_path = write_registry(
        """
        [servers.bad-server]
        id = "bad-server"
        display_name = "Bad Server"
        source_path = "src/bad-server"
        install_mode = "npm"
        launch_mode = "console_script"
        entrypoint = "bad-server"
        """
    )

    with pytest.raises(RegistryError, match="Unsupported install_mode"):
        load_registry(registry_path)


def test_script_mode_requires_requirements_path(write_registry):
    registry_path = write_registry(
        """
        [servers.script-server]
        id = "script-server"
        display_name = "Script Server"
        source_path = "src/script-server"
        install_mode = "script"
        launch_mode = "python_script"
        entrypoint = "src/script-server/server.py"
        """
    )

    with pytest.raises(RegistryError, match="requirements_path"):
        load_registry(registry_path)


def test_package_mode_rejects_requirements_path(write_registry):
    registry_path = write_registry(
        """
        [servers.package-server]
        id = "package-server"
        display_name = "Package Server"
        source_path = "src/package-server"
        install_mode = "package"
        launch_mode = "console_script"
        entrypoint = "package-server"
        requirements_path = "src/package-server/requirements.txt"
        """
    )

    with pytest.raises(RegistryError, match="must not define requirements_path"):
        load_registry(registry_path)
