from __future__ import annotations

import importlib
from pathlib import Path

from install.models import ServerSpec
from install.runtime_ops import build_runtime_plan


def _readiness_module():
    return importlib.import_module("install.readiness")


def _make_server_spec(**overrides: object) -> ServerSpec:
    values = {
        "id": "oci-api-mcp-server",
        "display_name": "OCI API MCP Server",
        "source_path": "src/oci-api-mcp-server",
        "install_mode": "package",
        "launch_mode": "console_script",
        "entrypoint": "oracle.oci-api-mcp-server",
        "python_version": "3.13",
        "requirements_path": None,
    }
    values.update(overrides)
    return ServerSpec(**values)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_classify_package_server_ready_when_console_script_exists(tmp_path: Path):
    readiness = _readiness_module()
    spec = _make_server_spec(entrypoint="oci-api-mcp")
    plan = build_runtime_plan(spec, tmp_path)
    _touch(plan.python_path)
    console_script = readiness.runtime_console_script_path(plan)
    _touch(console_script)

    result = readiness.classify_runtime_readiness(plan)

    assert result.server_id == spec.id
    assert result.status == "ready"
    assert result.missing_paths == ()


def test_classify_package_server_failed_when_runtime_python_is_missing(tmp_path: Path):
    readiness = _readiness_module()
    spec = _make_server_spec(entrypoint="oci-api-mcp")
    plan = build_runtime_plan(spec, tmp_path)
    console_script = readiness.runtime_console_script_path(plan)
    _touch(console_script)

    result = readiness.classify_runtime_readiness(plan)

    assert result.server_id == spec.id
    assert result.status == "failed"
    assert result.missing_paths == (plan.python_path,)


def test_classify_script_server_ready_when_python_and_entrypoint_exist(tmp_path: Path):
    readiness = _readiness_module()
    spec = _make_server_spec(
        id="dbtools-mcp-server",
        display_name="DBTools MCP Server",
        source_path="src/dbtools-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/dbtools-mcp-server/dbtools-mcp-server.py",
        requirements_path="src/dbtools-mcp-server/requirements.txt",
    )
    plan = build_runtime_plan(spec, tmp_path)
    _touch(plan.python_path)
    _touch(tmp_path / spec.entrypoint)

    result = readiness.classify_runtime_readiness(plan)

    assert result.server_id == spec.id
    assert result.status == "ready"
    assert result.missing_paths == ()


def test_classify_oracle_db_doc_server_blocked_when_docs_index_missing(tmp_path: Path):
    readiness = _readiness_module()
    user_home = tmp_path / "home"
    spec = _make_server_spec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
        readiness_check="oracle_db_doc_index",
    )
    plan = build_runtime_plan(spec, tmp_path)
    _touch(plan.python_path)
    _touch(tmp_path / spec.entrypoint)

    result = readiness.classify_runtime_readiness(plan, user_home=user_home)

    assert result.server_id == spec.id
    assert result.status == "blocked"
    assert result.missing_paths == (readiness.oracle_db_doc_index_path(user_home),)


def test_classify_oracle_db_doc_server_ready_when_docs_index_exists(tmp_path: Path):
    readiness = _readiness_module()
    user_home = tmp_path / "home"
    spec = _make_server_spec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
        readiness_check="oracle_db_doc_index",
    )
    plan = build_runtime_plan(spec, tmp_path)
    _touch(plan.python_path)
    _touch(tmp_path / spec.entrypoint)
    _touch(readiness.oracle_db_doc_index_path(user_home))

    result = readiness.classify_runtime_readiness(plan, user_home=user_home)

    assert result.server_id == spec.id
    assert result.status == "ready"
    assert result.missing_paths == ()


def test_classify_oracle_db_doc_server_respects_basic_readiness_check(tmp_path: Path):
    readiness = _readiness_module()
    spec = _make_server_spec(
        id="oracle-db-doc-mcp-server",
        display_name="Oracle DB Doc MCP Server",
        source_path="src/oracle-db-doc-mcp-server",
        install_mode="script",
        launch_mode="python_script",
        entrypoint="src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py",
        requirements_path="src/oracle-db-doc-mcp-server/requirements.txt",
        readiness_check="basic",
    )
    plan = build_runtime_plan(spec, tmp_path)
    _touch(plan.python_path)
    _touch(tmp_path / spec.entrypoint)

    result = readiness.classify_runtime_readiness(plan)

    assert result.server_id == spec.id
    assert result.status == "ready"
    assert result.missing_paths == ()


def test_classify_server_failed_when_expected_artifact_is_missing(tmp_path: Path):
    readiness = _readiness_module()
    spec = _make_server_spec(entrypoint="oci-api-mcp")
    plan = build_runtime_plan(spec, tmp_path)

    result = readiness.classify_runtime_readiness(plan)

    assert result.server_id == spec.id
    assert result.status == "failed"
    assert result.missing_paths == (plan.python_path, readiness.runtime_console_script_path(plan))
