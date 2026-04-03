# Local Installer

This installer builds per-server Python runtimes under `install/runtime/`, classifies readiness, and generates wrapper/config examples under `install/generated/`. It is Unix-only.

## Prerequisites

- Unix-like environment only. The generated wrappers target `bash` and `bin/` virtualenv layouts.
- Python 3.13 available to `uv`.
- `uv` installed and on `PATH`.
- Run commands from the repository root.
- Network access is typically required the first time runtimes are created because `uv pip install` may need to resolve package dependencies.
- Any server-specific credentials or environment still need to be configured separately. For example, OCI-backed servers still need working OCI configuration.

## Usage

Interactive mode prompts for a comma-separated selection:

```bash
uv run --python 3.13 python install/installer.py
```

Non-interactive mode passes the selection directly:

```bash
uv run --python 3.13 python install/installer.py --servers oci-iot-mcp-server
uv run --python 3.13 python install/installer.py --servers oci-iot-mcp-server,oci-api-mcp-server
```

Use `all` to target every installer-supported server in `install/servers.toml`. Today that means every registry entry the local installer knows how to provision as a Python package or Python script. `all` does not guarantee that every selected server will end up usable; runtime creation and readiness checks still determine what is actually rendered. If one selected server fails during runtime provisioning, the installer records that server as `failed`, continues the rest of the selection, and reports the final outcome in `install/generated/reports/`.

```bash
uv run --python 3.13 python install/installer.py --servers all
```

Use `--force` to remove and regenerate `install/generated/` before writing new wrappers, example configs, and reports.
Without `--force`, the installer still refreshes its managed generated subdirectories so wrappers, examples, and reports reflect the current ready-server set.
Re-running the installer against an existing runtime is supported; the per-server virtualenv is reused and the selected server package or requirements are refreshed in place.

By default, the installer prints a concise summary that includes the selected servers, readiness counts, and the generated artifact locations.

Use output-level flags to control how much it prints:

- `--silent`: suppress installer output.
- `--verbose`: include per-server readiness results.
- `--debug`: include per-server readiness plus runtime path details. This already includes the `--verbose` output, so `--verbose --debug` behaves the same as `--debug`.

## What Gets Written

Runtime environments are created per server under:

- `install/runtime/<server-id>/venv/`

Generated artifacts are written under:

- `install/generated/wrappers/<server-id>.sh`
- `install/generated/examples/codex.example.json`
- `install/generated/examples/vscode.mcp.json`
- `install/generated/reports/install-report.md`
- `install/generated/reports/install-report.json`

Wrappers start individual servers on demand using their own per-server runtime. Package servers execute the runtime-installed console script. Script servers execute the runtime Python plus the repo entrypoint and any configured launch arguments.

## Generated Configs

The Codex and VS Code files under `install/generated/` are generated examples only. The installer does not edit your real Codex or VS Code configuration.

To use them manually:

- Open `install/generated/examples/codex.example.json` and copy the desired `mcpServers` entries into your real Codex MCP configuration.
- Open `install/generated/examples/vscode.mcp.json` and copy the desired `servers` entries into your workspace `.vscode/mcp.json`.
- Only servers classified as `ready` are included in those example config files.

## Readiness States

- `ready`: expected runtime artifacts exist, so wrappers and example config entries are generated.
- `blocked`: the runtime exists, but an additional prerequisite is missing. Blocked servers are reported but not rendered into wrapper/config examples.
- `failed`: runtime provisioning failed or required runtime artifacts are missing. Failed servers are reported but not rendered into wrapper/config examples.

## Blocked Server Remediation

The main blocked case today is `oracle-db-doc-mcp-server`. Its runtime can be provisioned successfully and still be classified as `blocked` when the documentation index is missing at:

- `~/.oracle/oracle-db-doc-mcp-server/index.db`

Remediation:

1. Build the documentation index using the server’s `idx` mode.
2. Re-run the installer after the index exists.

Example from the repository root after the runtime has been created:

```bash
install/runtime/oracle-db-doc-mcp-server/venv/bin/python \
  src/oracle-db-doc-mcp-server/oracle-db-doc-mcp-server.py \
  idx -path /path/to/oracle-database-docs.zip
```

You can also point `-path` at an already extracted Oracle Database documentation directory. See the server-specific README for index-building details and prerequisites.

## Reading Results

The fastest way to understand what happened is to inspect:

- `install/generated/reports/install-report.md` for a human-readable summary
- `install/generated/reports/install-report.json` for structured output

Those reports include ready, blocked, and failed servers plus any missing artifact paths detected during readiness checks.
