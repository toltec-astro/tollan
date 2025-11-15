"""Tests for tollan.utils.typer module."""

from __future__ import annotations

import typer
from typer.testing import CliRunner

from tollan.utils.typer import create_cli


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
        result = runner.invoke(app, ["--help_all"])

        assert result.exit_code == 0
        # Should show main help
        assert "Usage:" in result.stdout
        # Should show individual command help with Rich Rule dividers
        assert "Command: cmd1" in result.stdout or "Command: cmd-1" in result.stdout
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

    def test_log_level_short_option(self):
        """Test -l short option for log level."""
        app = create_cli()

        @app.command()
        def test_cmd():
            """Test command."""
            typer.echo("Test output")

        runner = CliRunner()
        result = runner.invoke(app, ["-l", "DEBUG", "test_cmd"])

        assert result.exit_code == 0
        assert "Test output" in result.stdout

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
        assert "--log_level" in result.stdout or "-l" in result.stdout
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
