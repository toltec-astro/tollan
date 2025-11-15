"""Tests for log utilities."""

from __future__ import annotations

import time
from io import StringIO

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
            time.sleep(0.01)

        assert "test operation ..." in caplog.text
        assert "test operation done in" in caplog.text
        # Should show milliseconds for short duration
        assert "ms" in caplog.text

    def test_decorator(self, caplog):
        """Test timeit as decorator."""
        with caplog.at_level("DEBUG"):

            @timeit
            def slow_function():
                time.sleep(0.01)
                return 42

            result = slow_function()  # ty: ignore[missing-argument]

        assert result == 42
        assert "slow_function ..." in caplog.text
        assert "slow_function done in" in caplog.text

    def test_decorator_with_custom_message(self, caplog):
        """Test timeit decorator with custom message."""
        with caplog.at_level("DEBUG"):

            @timeit("Processing data")
            def process():
                time.sleep(0.01)

            process()

        assert "Processing data ..." in caplog.text
        assert "Processing data done in" in caplog.text

    def test_time_formatting(self):
        """Test time formatting function."""
        # Access the private _format_time method from timeit class
        format_func = timeit._format_time

        # Test milliseconds (short duration)
        result = format_func(0.001)
        assert "ms" in result or "1ms" in result

        # Test milliseconds for longer duration
        result = format_func(0.01)
        assert "ms" in result or "10ms" in result

        # Test transition to human_time (>15ms uses astropy.utils.human_time)
        result = format_func(1.5)
        assert "s" in result.lower() or "sec" in result.lower()

        # Test hours (astropy.utils.human_time formats this)
        result = format_func(3700)
        # human_time will format this as hours
        assert (
            "hr" in result.lower() or "hour" in result.lower() or "h" in result.lower()
        )


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
