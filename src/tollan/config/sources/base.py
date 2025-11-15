"""Base classes and utilities for configuration sources."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from simpleeval import NameNotDefined, simple_eval

from ...utils.log import logger

__all__ = [
    "ConfigSourceBase",
    "DictConfigT",
]


type DictConfigT = dict[str | int, Any]


class ConfigSourceBase(BaseModel):
    """Base class for configuration sources.

    Common attributes and behavior for all config source types.
    """

    model_config = {"frozen": True}

    order: int
    name: str | None = None
    enabled: bool = True
    enable_if: str | None = None

    def is_enabled_for(self, context: dict[str, Any] | None = None) -> bool:
        """Check if this source is enabled for the given context.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary for evaluating enable_if condition

        Returns
        -------
        bool
            True if source should be loaded, False otherwise
        """
        if not self.enabled:
            return False

        if self.enable_if is None:
            return True

        if context is None:
            context = {}

        # Evaluate enable_if expression using safe eval
        try:
            result = _safe_eval(self.enable_if, context)
            return bool(result)
        except (ValueError, NameError, NameNotDefined, SyntaxError) as e:
            logger.warning(
                f"Failed to evaluate enable_if '{self.enable_if}' "
                f"with context {context}: {e}",
            )
            return False

    def load(self, context: dict[str, Any] | None = None) -> DictConfigT:
        """Load configuration data from this source.

        Must be implemented by subclasses.

        Parameters
        ----------
        context : dict[str, Any] | None, optional
            Context dictionary for conditional loading

        Returns
        -------
        DictConfigT
            Configuration dictionary
        """
        raise NotImplementedError


def _safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """Safely evaluate an expression using simpleeval.

    Uses the simpleeval library for safe expression evaluation without eval().
    Supports comparison operators, boolean logic, and basic operations.

    Parameters
    ----------
    expr : str
        Expression to evaluate
    context : dict[str, Any]
        Variables available in the expression (passed as 'names' to simpleeval)

    Returns
    -------
    Any
        Result of the expression

    Raises
    ------
    ValueError
        If expression contains disallowed operations
    NameError
        If variable not found in context
    """
    try:
        return simple_eval(expr, names=context)
    except NameError as e:
        msg = f"Variable not found in context: {e}"
        raise NameError(msg) from e
