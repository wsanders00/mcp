from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def write_registry(tmp_path: Path):
    def _write(contents: str) -> Path:
        registry_path = tmp_path / "servers.toml"
        registry_path.write_text(textwrap.dedent(contents).strip() + "\n", encoding="utf-8")
        return registry_path

    return _write
