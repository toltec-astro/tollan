"""Tests for log utilities."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest

from tollan.utils.log import logged_closing, logger, logit, timeit


@pytest.fixture
def caplog(caplog):
    """Configure caplog to capture loguru logs."""
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,
    )
    yield caplog
    logger.remove(handler_id)


class TestLogit:
    """Tests for logit decorator/context manager."""

    def test_context_manager(self, caplog):
        """Test logit as context manager."""
        with logit(logger.info, "test operation"):
            pass

        assert "test operation ..." in caplog.text
        assert "test operation done" in caplog.text

    def test_decorator(self, caplog):
        """Test logit as decorator."""

        @logit(logger.info, "test function")
        def my_function():
            return 42

        result = my_function()

        assert result == 42
        assert "test function ..." in caplog.text
        assert "test function done" in caplog.text

    def test_custom_log_level(self, caplog):
        """Test logit with custom log level."""
        with logit(logger.debug, "debug operation"):
            pass

        assert "debug operation ..." in caplog.text
        assert "debug operation done" in caplog.text


class TestLoggedClosing:
    """Tests for logged_closing context manager."""

    def test_closes_with_logging(self, caplog):
        """Test that object is closed and logged."""
        mock_file = StringIO("test")

        with logged_closing(logger.info, mock_file):
            assert not mock_file.closed

        assert mock_file.closed
        assert "close" in caplog.text
        assert "done" in caplog.text

    def test_custom_message(self, caplog):
        """Test with custom message."""
        mock_file = StringIO("test")

        with logged_closing(logger.info, mock_file, "closing file"):
            pass

        assert mock_file.closed
        assert "closing file ..." in caplog.text
        assert "closing file done" in caplog.text


class TestTimeit:
    """Tests for timeit decorator/context manager."""

    def test_context_manager(self, caplog):
        """Test timeit as context manager."""
        with caplog.at_level("DEBUG"), timeit("test operation"):
            pass

        assert "test operation ..." in caplog.text
        assert "test operation done in" in caplog.text
        # Should show milliseconds for short duration
        assert "ms" in caplog.text

    def test_decorator(self, caplog):
        """Test timeit as decorator."""
        with caplog.at_level("DEBUG"):

            @timeit
            def slow_function():
                return 42

            result = slow_function()

        assert result == 42
        assert "slow_function ..." in caplog.text
        assert "slow_function done in" in caplog.text

    def test_decorator_with_custom_message(self, caplog):
        """Test timeit decorator with custom message."""
        with caplog.at_level("DEBUG"):

            @timeit("Processing data")
            def process():
                pass

            process()

        assert "Processing data ..." in caplog.text
        assert "Processing data done in" in caplog.text

    @pytest.mark.parametrize(
        ("elapsed", "expected"), [(0.01, "10ms"), (1.5, "1500ms"), (3700, "1h 1m")]
    )
    def test_elapsed_time_in_context_log(self, elapsed, expected, caplog, monkeypatch):
        """Report the measured interval through the public context manager."""
        from tollan.utils import log as log_utils

        readings = iter([100.0, 100.0 + elapsed])
        monkeypatch.setattr(
            log_utils, "time", SimpleNamespace(time=lambda: next(readings))
        )
        with caplog.at_level("DEBUG"), timeit("operation"):
            pass
        assert f"operation done in {expected}" in caplog.text

    @pytest.mark.parametrize("wrapper", [logit, timeit])
    def test_decorator_propagates_exceptions(self, wrapper, caplog):
        """Logging must preserve failures from application work."""
        error = ValueError("operation failed")
        decorator = logit(logger.info, "operation") if wrapper is logit else timeit

        @decorator
        def operation():
            raise error

        with caplog.at_level("DEBUG"), pytest.raises(ValueError) as caught:
            operation()
        assert caught.value is error
        assert "operation ..." in caplog.text


class TestLogger:
    """Tests for logger instance."""

    def test_logger_exists(self):
        """Test that logger is imported correctly."""
        assert logger is not None

    def test_logger_basic_logging(self, caplog):
        """Test basic logging functionality."""
        logger.info("Test message")

        assert "Test message" in caplog.text

    def test_logger_levels(self, caplog):
        """Test different log levels."""
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        assert "Debug message" in caplog.text
        assert "Info message" in caplog.text
        assert "Warning message" in caplog.text
        assert "Error message" in caplog.text
