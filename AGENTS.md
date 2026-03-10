# Repository Guidelines

## Project Structure & Module Organization

This repository is a polyglot collection of MCP server reference implementations. Most active packages live under `src/<server-name>/` with their own `pyproject.toml`, `README.md`, and package code under `oracle/<server_name>/`. Common patterns are `server.py` for entrypoints and `models.py` for schemas. Shared helpers and generators live in `scripts/`. End-to-end coverage lives in `tests/e2e/features/` with `.feature` files, step definitions in `tests/e2e/features/steps/`, and test fixtures in `tests/e2e/features/mocks/`.

## Build, Test, and Development Commands

Use `uv` and the root `Makefile` for the default workflow:

- `make sync`: install locked dev dependencies for each `src/*` package.
- `make build`: build all package distributions with `uv build`.
- `make lint`: run `tox -e lint` from the repo root.
- `make format`: apply `isort`, `black`, and `flake8` checks/fixes from the root config.
- `make test`: run package-local `pytest` with coverage, then combine reports.
- `SUBDIRS=src/oci-api-mcp-server make test`: limit work to one package while iterating.
- `make e2e-tests`: build/install packages, then run `behave tests/e2e/features`.

## Coding Style & Naming Conventions

For the main Python packages, use 4-space indentation, Black-compatible formatting, `isort` import ordering, and a 110-character line limit from `tox.ini`. Prefer snake_case for modules and functions, hyphenated directory names for server packages, and keep package entrypoints in `server.py`. Most packages target Python 3.13. Check the local `pyproject.toml` before editing standalone packages such as `oci-pricing-mcp-server`, which uses Black/Ruff with a 100-character limit.

## Testing Guidelines

Add unit tests as `test_*.py` files so `pytest` discovers them cleanly. Keep tests close to the package they validate, and include async coverage when server code is coroutine-based. Package coverage thresholds are enforced locally in each `pyproject.toml`; the root combined report must stay above `69%`. For E2E work, copy `tests/e2e/features/.env.template` to `.env` and run targeted scenarios with `behave -n "<scenario name>"`.

## Commit & Pull Request Guidelines

Recent history follows short conventional prefixes such as `feat:` and `fix:`; keep that pattern, optionally with the repo’s existing emoji tags. All commits for PRs must be signed off (`git commit -s`) to satisfy the Oracle Contributor Agreement process. Open or reference an issue, fill in the PR template completely, describe validation steps, and update docs or samples when behavior changes.

## Security & Configuration Tips

Do not commit OCI credentials, `.env` files, or local MCP host configs with secrets. When documenting OCI mounts or config paths, prefer `~/.oci`-style paths so examples work both locally and in containers.
