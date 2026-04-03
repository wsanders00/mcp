from __future__ import annotations

import importlib

import pytest


def _installer_module():
    return importlib.import_module("install.installer")


def test_build_parser_accepts_servers_option():
    parser = _installer_module().build_parser()

    args = parser.parse_args(["--servers", "oci-api-mcp-server"])

    assert args.servers == "oci-api-mcp-server"
    assert args.force is False


def test_build_parser_accepts_force_flag():
    parser = _installer_module().build_parser()

    args = parser.parse_args(["--force"])

    assert args.servers is None
    assert args.force is True


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--silent", "silent"),
        ("--verbose", "verbose"),
        ("--debug", "debug"),
    ],
)
def test_build_parser_accepts_output_level_flags(flag, expected):
    parser = _installer_module().build_parser()

    args = parser.parse_args([flag])

    assert args.output_level == expected


@pytest.mark.parametrize(
    "argv",
    [
        ["--verbose", "--debug"],
        ["--debug", "--verbose"],
    ],
)
def test_build_parser_accepts_debug_and_verbose_together(argv):
    parser = _installer_module().build_parser()

    args = parser.parse_args(argv)

    assert args.output_level == "debug"


def test_choose_selection_uses_explicit_servers_and_normalizes_spacing():
    installer = _installer_module()
    args = installer.build_parser().parse_args(
        ["--servers", " oci-api-mcp-server , dbtools-mcp-server "]
    )

    def unexpected_prompt(_prompt: str) -> str:
        pytest.fail("choose_selection prompted despite --servers being provided")

    selection = installer.choose_selection(args, input_fn=unexpected_prompt)

    assert selection == "oci-api-mcp-server,dbtools-mcp-server"


def test_choose_selection_prompts_when_servers_arg_is_missing():
    installer = _installer_module()
    args = installer.build_parser().parse_args([])
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return " oracle-db-doc-mcp-server , dbtools-mcp-server "

    selection = installer.choose_selection(args, input_fn=fake_input)

    assert selection == "oracle-db-doc-mcp-server,dbtools-mcp-server"
    assert prompts == ["Select server(s) to install (comma-separated or 'all'): "]


def test_choose_selection_uses_runtime_default_input(monkeypatch):
    installer = _installer_module()
    args = installer.build_parser().parse_args([])
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return " dbtools-mcp-server "

    monkeypatch.setattr("builtins.input", fake_input)

    selection = installer.choose_selection(args)

    assert selection == "dbtools-mcp-server"
    assert prompts == ["Select server(s) to install (comma-separated or 'all'): "]


def test_choose_selection_supports_all_keyword():
    installer = _installer_module()
    args = installer.build_parser().parse_args([])

    selection = installer.choose_selection(args, input_fn=lambda _prompt: "  all  ")

    assert selection == "all"


@pytest.mark.parametrize(
    ("argv", "prompt_response"),
    [
        (["--servers", "   "], None),
        ([], "   "),
    ],
)
def test_choose_selection_rejects_empty_input(argv, prompt_response):
    installer = _installer_module()
    args = installer.build_parser().parse_args(argv)

    def fake_input(_prompt: str) -> str:
        assert prompt_response is not None
        return prompt_response

    input_fn = fake_input if prompt_response is not None else input

    with pytest.raises(ValueError, match="Selection must not be empty"):
        installer.choose_selection(args, input_fn=input_fn)


@pytest.mark.parametrize(
    ("raw_selection", "expected"),
    [
        (" oci-api-mcp-server , dbtools-mcp-server ", "oci-api-mcp-server,dbtools-mcp-server"),
        ([" oracle-db-doc-mcp-server ", "dbtools-mcp-server "], "oracle-db-doc-mcp-server,dbtools-mcp-server"),
    ],
)
def test_choose_selection_accepts_raw_string_and_iterable_inputs(raw_selection, expected):
    installer = _installer_module()

    def unexpected_prompt(_prompt: str) -> str:
        pytest.fail("choose_selection prompted despite a raw selection being provided")

    selection = installer.choose_selection(raw_selection, input_fn=unexpected_prompt)

    assert selection == expected
