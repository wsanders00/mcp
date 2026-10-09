"""Offline entry point tests; no listener, credential store or OCI calls."""
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v1.0 as shown at
# https://oss.oracle.com/licenses/upl.

import json
from unittest.mock import patch

import pytest

from oracle.oci_iot_mcp_server import server


def test_fixture_entry_private_config_and_no_stdio_start(tmp_path):
    config = tmp_path / "callers.json"
    config.write_text(json.dumps({"a" * 48: "caller-a"}))
    config.chmod(0o600)
    args = ["server", "--offline-fixture-http", "--caller-config", str(config)]
    with patch("sys.argv", args), patch("uvicorn.run") as run, patch.object(server.mcp, "run") as stdio:
        server.main()
    run.assert_called_once()
    assert run.call_args.kwargs == {"host": "127.0.0.1", "port": 8765,
                                    "access_log": False, "log_level": "warning"}
    stdio.assert_not_called()


@pytest.mark.parametrize("kind", ["broad_mode", "symlink", "bad_json", "missing", "bad_mapping"])
def test_fixture_entry_rejects_bad_configuration_without_echo(tmp_path, kind):
    config = tmp_path / "private-input-marker.json"
    config.write_text(json.dumps({"a" * 48: "caller-a"}))
    config.chmod(0o600)
    if kind == "broad_mode":
        config.chmod(0o644)
    elif kind == "symlink":
        target = tmp_path / "actual.json"
        config.rename(target)
        config.symlink_to(target)
    elif kind == "bad_json":
        config.write_text("private-payload-marker")
    elif kind == "missing":
        config.unlink()
    elif kind == "bad_mapping":
        config.write_text("[]")
    args = ["server", "--offline-fixture-http", "--caller-config", str(config)]
    with patch("sys.argv", args), patch("uvicorn.run") as run:
        with pytest.raises(RuntimeError, match="^fixture_configuration_invalid$") as error:
            server.main()
    assert "private" not in str(error.value)
    run.assert_not_called()
