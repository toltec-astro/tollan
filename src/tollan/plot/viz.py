"""Configured visualizations for standalone use and pipeline artifacts.

Visualization consumes data and returns native presentation objects. Concrete
visualizations define the input representation they accept. Their outputs can be
used directly in a notebook or application, or selected for retention with their
specification in an ArtifactContext.
"""

from ..pipeline.artifact import ArtifactSpec

__all__ = ["VizBase"]


class VizBase[DataT](ArtifactSpec[DataT]):
    """Configuration base for constructing and presenting visualizations.

    Subclasses define ``__call__`` for their typed inputs. Reusable builders can
    use instance settings or receive settings explicitly through their inputs.
    Construction returns the native presentation object without starting a server
    or writing files. Use ``show`` or ``write`` with that object afterward.
    """

    def show(self, data: DataT) -> None:
        """Display an already constructed visualization.

        Parameters
        ----------
        data : DataT
            Native presentation object produced by this visualization.

        Returns
        -------
        None
            The concrete backend controls the display lifetime.

        Raises
        ------
        NotImplementedError
            This visualization has no display implementation.
        """
        raise NotImplementedError
