"""Tests for the tollan package entry point (python -m tollan)."""

from __future__ import annotations


def test_import_main():
    """Importing __main__ runs the module and loads the CLI app."""
    import tollan.__main__

    assert hasattr(tollan.__main__, "app")
