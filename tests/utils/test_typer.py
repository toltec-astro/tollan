"""Tests for tollan.utils.typer module."""

from __future__ import annotations

from typing import Annotated

import pytest
import typer
from typer.testing import CliRunner

from tollan.utils.typer import MultiOption, TollanTyper, create_cli


@pytest.mark.parametrize("factory", [TollanTyper, create_cli])
def test_python_names_and_explicit_aliases(factory):
    app = factory()

    @app.command()
    def inspect_config(
        *,
        data_root: str = "default",
        show_config: bool = True,
        env_files: Annotated[list[str] | None, MultiOption()] = None,
        custom_path: Annotated[str, typer.Option("--custom-path", "-p")] = "default",
        custom_flag: Annotated[bool, typer.Option("--on/--off")] = False,
    ):
        typer.echo(f"{data_root}|{show_config}|{env_files}|{custom_path}|{custom_flag}")

    prefix = [] if factory is TollanTyper else ["inspect_config"]
    runner = CliRunner()
    for alias in ("--custom-path", "-p"):
        result = runner.invoke(
            app,
            [
                *prefix,
                "--data_root",
                "here",
                "--no_show_config",
                "--env_files",
                "a",
                "b",
                "--env_files",
                "c",
                alias,
                "there",
                "--on",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "here|False|['a', 'b', 'c']|there|True" in result.stdout
    help_result = runner.invoke(app, [*prefix, "--help"])
    assert "--data_root" in help_result.stdout
    assert "--data-root" not in help_result.stdout
    assert runner.invoke(app, [*prefix, "--data-root", "here"]).exit_code == 2


def test_shared_callback_does_not_change_plain_typer():
    plain = typer.Typer()
    tollan = TollanTyper()
    option = typer.Option("default", metavar="DIRECTORY")

    @plain.command()
    @tollan.command()
    def inspect_config(data_root: str = option):
        typer.echo(data_root)

    runner = CliRunner()
    for app, flag in (
        (tollan, "--data_root"),
        (plain, "--data-root"),
        (tollan, "--data_root"),
    ):
        result = runner.invoke(app, [flag, "here"])
        assert result.exit_code == 0, result.output
        assert result.stdout == "here\n"
    assert not option.param_decls
    assert typer.main.get_command_name("inspect_config") == "inspect-config"


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["child", "run"], ["INFO"]),
        (["--log_level", "DEBUG", "child", "run"], ["DEBUG"]),
        (["child", "--log_level", "WARNING", "run"], ["INFO", "WARNING"]),
        (
            ["--log_level", "DEBUG", "child", "--log_level", "WARNING", "run"],
            ["DEBUG", "WARNING"],
        ),
        (
            ["--log_level", "DEBUG", "--log_level", "WARNING", "child", "run"],
            ["WARNING"],
        ),
    ],
)
def test_log_levels_at_each_group(embedded, args, expected, monkeypatch):
    from tollan.utils import typer as typer_utils

    levels = []
    monkeypatch.setattr(
        typer_utils, "reset_logger", lambda *, level, verbose: levels.append(level)
    )
    app = TollanTyper()
    child = TollanTyper()
    app.add_typer(child, name="child")
    seen = []

    @app.callback()
    def main(ctx: typer.Context):
        seen.append(ctx.params.copy())

    @child.callback()
    def child_main(ctx: typer.Context):
        seen.append(ctx.params.copy())

    @child.command()
    def run():
        pass

    if embedded:
        host = typer.Typer()
        host.add_typer(app, name="plugin")
        args = ["plugin", *args]
    else:
        host = app
    result = CliRunner().invoke(host, args)
    assert result.exit_code == 0, result.output
    assert levels == expected
    assert seen == [{}, {}]


@pytest.mark.parametrize("nested", [False, True])
def test_application_can_use_short_l_for_its_own_option(nested, monkeypatch):
    from tollan.utils import typer as typer_utils

    levels = []
    monkeypatch.setattr(
        typer_utils, "reset_logger", lambda *, level, verbose: levels.append(level)
    )
    app = create_cli()
    group = TollanTyper() if nested else app
    if nested:
        app.add_typer(group, name="tools")
    locations = []

    @group.callback()
    def main(location: Annotated[str | None, typer.Option("--location", "-l")] = None):
        locations.append(location)

    @group.command()
    def run():
        pass

    prefix = ["tools"] if nested else []
    result = CliRunner().invoke(
        app, [*prefix, "-l", "here", "--log_level", "DEBUG", "run"]
    )
    assert result.exit_code == 0, result.output
    assert locations == ["here"]
    assert levels == (["INFO", "DEBUG"] if nested else ["DEBUG"])


def test_regular_typer_ancestor_logging_is_preserved(monkeypatch):
    from tollan.utils import typer as typer_utils

    levels = []
    monkeypatch.setattr(
        typer_utils, "reset_logger", lambda *, level, verbose: levels.append(level)
    )
    host = typer.Typer()
    plugin = create_cli()
    host.add_typer(plugin, name="plugin")

    @host.callback()
    def main(log_level: Annotated[str | None, typer.Option("--log_level")] = None):
        if log_level is not None:
            typer_utils.reset_logger(level=log_level, verbose=False)

    runner = CliRunner()
    result = runner.invoke(host, ["--log_level", "DEBUG", "plugin", "version"])
    assert result.exit_code == 0, result.output
    assert levels == ["DEBUG"]
    levels.clear()
    result = runner.invoke(host, ["plugin", "version"])
    assert result.exit_code == 0, result.output
    assert levels == ["INFO"]


def test_embedded_group_options_and_log_level_validation():
    host = typer.Typer()
    plugin = create_cli()
    nested = create_cli()
    plugin.add_typer(nested, name="nested")
    host.add_typer(plugin, name="plugin")
    runner = CliRunner()
    for prefix in (["plugin"], ["plugin", "nested"]):
        help_result = runner.invoke(host, [*prefix, "--help"])
        assert help_result.exit_code == 0, help_result.output
        assert "--help_all" in help_result.stdout
        assert "--log_level" in help_result.stdout
        assert "DEBUG" in help_result.stdout
        result = runner.invoke(host, [*prefix, "--log_level", "INVALID", "version"])
        assert result.exit_code == 2, result.output
        assert "Invalid value" in result.output
    result = runner.invoke(host, ["plugin", "--help_all"], prog_name="host")
    assert result.exit_code == 0, result.output
    assert "Usage: host plugin nested" in " ".join(result.stdout.split())
    assert "Usage: host plugin nested version" not in " ".join(result.stdout.split())
    root_help = runner.invoke(host, ["--help"])
    assert "--log_level" not in root_help.stdout
    assert "--help_all" not in root_help.stdout


@pytest.mark.parametrize("rich_markup_mode", [None, "rich"])
@pytest.mark.parametrize("depth", [0, 1, 2])
def test_help_all_only_immediate_children(rich_markup_mode, depth):
    app = TollanTyper(rich_markup_mode=rich_markup_mode)
    tools = TollanTyper(rich_markup_mode=rich_markup_mode)
    formats = TollanTyper(rich_markup_mode=rich_markup_mode)
    app.add_typer(tools, name="tools")
    tools.add_typer(formats, name="formats")
    calls = []

    @app.callback()
    def main(root_value: str = typer.Option(...)):
        calls.append("root")

    @tools.callback()
    def tools_main():
        calls.append("tools")

    @formats.callback()
    def formats_main():
        calls.append("formats")

    def validate(value):
        calls.append("parameter")
        return value

    @formats.command(hidden=True)
    def convert(
        input_path: str,
        leaf_option: str = typer.Option(..., callback=validate, prompt=True),
    ):
        """Detailed leaf documentation."""
        calls.append("leaf")

    @app.command()
    def sibling():
        """Sibling documentation."""
        calls.append("sibling")

    args = ["--root_value", "here", *["tools", "formats"][:depth]] if depth else []
    result = CliRunner().invoke(app, [*args, "--help_all"], prog_name="app")
    assert result.exit_code == 0, result.output
    output = " ".join(result.stdout.split())
    paths = ["app", "app tools", "app tools formats", "app tools formats convert"]
    assert f"Usage: {paths[depth]} " in output
    assert f"Usage: {paths[depth + 1]} " in output
    assert f"Command: {paths[depth + 1]}" in output
    if depth < 2:
        assert f"Usage: {paths[depth + 2]}" not in output
    assert ("--leaf_option" in output) == (depth == 2)
    assert ("Detailed leaf documentation." in output) == (depth == 2)
    assert result.stdout.count("Usage:") == (3 if depth == 0 else 2)
    assert ("Sibling documentation." in output) == (depth == 0)
    assert calls == ["root", "tools"][:depth]


@pytest.mark.parametrize("rich_markup_mode", [None, "rich"])
@pytest.mark.parametrize("color", [False, True])
def test_help_all_pages_match_regular_help(rich_markup_mode, color):
    app = TollanTyper(
        rich_markup_mode=rich_markup_mode,
        context_settings={"color": color, "terminal_width": 120},
    )

    @app.callback()
    def main():
        """Inspect files."""

    @app.command()
    def inspect_file(count: int = 1):
        """Read [red]literal text[/red] and 123 items."""

    runner = CliRunner()
    root_help = runner.invoke(app, ["--help"], prog_name="app", color=color)
    child_help = runner.invoke(
        app, ["inspect_file", "--help"], prog_name="app", color=color
    )
    all_help = runner.invoke(app, ["--help_all"], prog_name="app", color=color)
    for result in (root_help, child_help, all_help):
        assert result.exit_code == 0, result.output
    assert all_help.stdout.startswith(root_help.stdout)
    assert all_help.stdout.endswith(child_help.stdout)


def test_group_multi_option_does_not_rewrite_child_arguments():
    app = TollanTyper()

    @app.callback()
    def main(env_files: Annotated[list[str] | None, MultiOption()] = None):
        typer.echo(f"group:{env_files}")

    @app.command("explicit-command")
    def custom_name(env_files: Annotated[list[str] | None, typer.Option()] = None):
        typer.echo(f"child:{env_files}")

    result = CliRunner().invoke(
        app,
        [
            "--env_files",
            "a",
            "b",
            "--",
            "explicit-command",
            "--env_files",
            "c",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "group:['a', 'b']" in result.stdout
    assert "child:['c']" in result.stdout
    # A normal repeatable option on the child must not become variadic.
    result = CliRunner().invoke(app, ["explicit-command", "--env_files", "c", "d"])
    assert result.exit_code == 2


def test_multi_option_leaves_separator_tail_unchanged():
    app = TollanTyper()

    @app.command(context_settings={"allow_extra_args": True})
    def run(
        ctx: typer.Context, env_files: Annotated[list[str] | None, MultiOption()] = None
    ):
        typer.echo(str((env_files, ctx.args)))

    result = CliRunner().invoke(
        app, ["--env_files", "a", "b", "--", "--env_files", "c", "d"]
    )
    assert result.exit_code == 0, result.output
    assert "(['a', 'b'], ['--env_files', 'c', 'd'])" in result.stdout


class TestCreateCli:
    """Tests for create_cli function."""

    def test_create_basic_app(self):
        """Test creating a basic CLI app."""
        app = create_cli()

        assert isinstance(app, typer.Typer)

    def test_create_app_with_version(self):
        """Test creating app with custom version."""
        app = create_cli(version="1.2.3")

        assert isinstance(app, typer.Typer)

    def test_command_execution(self):
        """Test that commands execute correctly."""
        app = create_cli()

        @app.command()
        def echo_cmd(message: str):
            """Echo a message."""
            typer.echo(f"Message: {message}")

        runner = CliRunner()
        result = runner.invoke(app, ["echo_cmd", "Hello"])

        assert result.exit_code == 0
        assert "Message: Hello" in result.stdout

    def test_multiple_commands(self):
        """Test app with multiple commands."""
        app = create_cli()

        @app.command()
        def cmd1():
            """First command."""
            typer.echo("Command 1")

        @app.command()
        def cmd2():
            """Second command."""
            typer.echo("Command 2")

        runner = CliRunner()

        result1 = runner.invoke(app, ["cmd1"])
        assert "Command 1" in result1.stdout

        result2 = runner.invoke(app, ["cmd2"])
        assert "Command 2" in result2.stdout

    def test_help_option_works(self):
        """Test that --help option displays help."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout

    def test_command_help_works(self):
        """Test that command help works."""
        app = create_cli()

        @app.command()
        def test_cmd(arg: str):
            """
            Test command with argument.

            Args:
                arg: Test argument
            """

        runner = CliRunner()
        result = runner.invoke(app, ["test_cmd", "--help"])

        assert result.exit_code == 0
        assert "Test command with argument" in result.stdout

    def test_help_short_option(self):
        """Test that -h also works for help."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""

        runner = CliRunner()
        result = runner.invoke(app, ["-h"])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout

    def test_commands_listed_in_help(self):
        """Test that all commands are listed in help."""
        app = create_cli()

        @app.command()
        def cmd1():
            """First command."""

        @app.command()
        def cmd2():
            """Second command."""

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        # Version command is automatically added
        assert "version" in result.stdout.lower()
        # Custom commands should be listed (typer converts underscores to hyphens)
        assert "cmd1" in result.stdout or "cmd-1" in result.stdout
        assert "cmd2" in result.stdout or "cmd-2" in result.stdout

    def test_help_all_option(self):
        """Test --help_all option shows detailed help for all commands."""
        app = create_cli()

        @app.command()
        def cmd1(arg: str):
            """First command with arg."""
            typer.echo(f"Command 1: {arg}")

        @app.command()
        def cmd2(arg: str):
            """Second command with arg."""
            typer.echo(f"Command 2: {arg}")

        runner = CliRunner()
        result = runner.invoke(app, ["--help_all"], prog_name="app")

        assert result.exit_code == 0
        # Should show main help
        assert "Usage:" in result.stdout
        # Should show individual command help with Rich Rule dividers
        assert "Command: app cmd1" in result.stdout
        assert "First command with arg" in result.stdout

    def test_log_level_option(self):
        """Test --log_level option is available."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""
            typer.echo("Running test command")

        runner = CliRunner()

        # Test with DEBUG level
        result = runner.invoke(app, ["--log_level", "DEBUG", "test_cmd"])
        assert result.exit_code == 0
        assert "Running test command" in result.stdout

        # Test with INFO level
        result = runner.invoke(app, ["--log_level", "INFO", "test_cmd"])
        assert result.exit_code == 0

        # Test with WARNING level
        result = runner.invoke(app, ["--log_level", "WARNING", "test_cmd"])
        assert result.exit_code == 0

    def test_log_level_has_no_short_option(self):
        """Logging requires the explicit --log_level option."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""
            typer.echo("Test output")

        runner = CliRunner()
        result = runner.invoke(app, ["-l", "DEBUG", "test_cmd"])

        assert result.exit_code == 2
        assert "Test output" not in result.stdout

    def test_custom_options_in_help(self):
        """Test that --help_all and --log_level appear in help."""
        app = create_cli()

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Check for --help_all option
        assert "--help_all" in result.stdout
        assert "Show full help" in result.stdout
        # Check for --log_level option
        assert "--log_level" in result.stdout
        assert "log level" in result.stdout.lower()

    def test_no_command_shows_help(self):
        """Test that running without a command shows help."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""

        runner = CliRunner()
        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout
        assert "Commands" in result.stdout
