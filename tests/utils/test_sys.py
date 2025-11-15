"""Tests for tollan.utils.sys module."""

from __future__ import annotations

import os
import pwd
import socket
from unittest.mock import MagicMock, patch

from tollan.utils.sys import get_hostname, get_username, pty_run


class TestGetUsername:
    """Test get_username function."""

    def test_get_username(self):
        """Test retrieving current username."""
        username = get_username()
        assert isinstance(username, str)
        assert len(username) > 0

    def test_get_username_matches_os(self):
        """Test that username matches OS UID lookup."""
        uid = os.getuid()
        expected = pwd.getpwuid(uid).pw_name
        assert get_username() == expected

    def test_get_username_mocked(self):
        """Test get_username with mocked pwd."""
        mock_pwent = MagicMock()
        mock_pwent.pw_name = "testuser"
        with patch("pwd.getpwuid", return_value=mock_pwent):
            assert get_username() == "testuser"


class TestGetHostname:
    """Test get_hostname function."""

    def test_get_hostname(self):
        """Test retrieving system hostname."""
        hostname = get_hostname()
        assert isinstance(hostname, str)
        assert len(hostname) > 0

    def test_get_hostname_matches_socket(self):
        """Test that hostname matches socket.gethostname()."""
        expected = socket.gethostname()
        assert get_hostname() == expected

    def test_get_hostname_mocked(self):
        """Test get_hostname with mocked socket."""
        with patch("socket.gethostname", return_value="test-machine"):
            assert get_hostname() == "test-machine"


class TestPtyRun:
    """Test pty_run function."""

    def test_pty_run_with_string_command(self):
        """Test pty_run with string command."""
        with patch("pty.spawn", return_value=0) as mock_spawn:
            result = pty_run("echo hello")
            assert result == 0
            mock_spawn.assert_called_once_with(["echo", "hello"])

    def test_pty_run_with_list_command(self):
        """Test pty_run with list command."""
        with patch("pty.spawn", return_value=0) as mock_spawn:
            result = pty_run(["echo", "hello world"])
            assert result == 0
            mock_spawn.assert_called_once_with(["echo", "hello world"])

    def test_pty_run_nonzero_exit(self):
        """Test pty_run returns nonzero exit code."""
        with patch("pty.spawn", return_value=1) as mock_spawn:
            result = pty_run("false")
            assert result == 1
            mock_spawn.assert_called_once()

    def test_pty_run_command_with_args(self):
        """Test pty_run with command and arguments."""
        with patch("pty.spawn", return_value=0) as mock_spawn:
            result = pty_run(["ls", "-la", "/tmp"])  # noqa: S108
            assert result == 0
            mock_spawn.assert_called_once_with(["ls", "-la", "/tmp"])  # noqa: S108

    def test_pty_run_converts_to_strings(self):
        """Test that pty_run converts arguments to strings."""
        with patch("pty.spawn", return_value=0) as mock_spawn:
            result = pty_run(["echo", 123, True])  # type: ignore[list-item]
            assert result == 0
            # All arguments should be converted to strings
            mock_spawn.assert_called_once_with(["echo", "123", "True"])
