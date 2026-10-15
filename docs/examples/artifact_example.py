"""Create signal diagnostics, retain their specs, and export them on demand."""

from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.graph_objects as go
from pydantic import Field

from tollan.config.types import AnyPath  # noqa: TC001 -- Pydantic field type.
from tollan.pipeline import (
    ArtifactContext,
    ArtifactFile,
    ArtifactSpec,
    Step,
    StepConfig,
    StepContext,
)
from tollan.plot.plotly import (
    PlotlyFigExport,
    PlotlyFigExportFormat,
    PlotlyFigShowInDash,
    PlotlyViz,
)

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    import xarray as xr


class SignalViz(PlotlyViz):
    """Signal trace with a configurable line width."""

    line_width: float = Field(default=2.0, gt=0)

    def __call__(self, values: np.ndarray) -> go.Figure:
        """Return a signal trace for a one-dimensional sample array."""
        return self.make_figure(values, line_width=self.line_width)

    @classmethod
    def make_figure(cls, values: np.ndarray, *, line_width: float) -> go.Figure:
        """Return a signal trace with an explicit line width."""
        return go.Figure(
            go.Scatter(y=values, mode="lines", line={"width": line_width}),
            layout={"title": "Signal", "xaxis_title": "Sample", "yaxis_title": "Value"},
        )


class HistogramViz(PlotlyViz):
    """Sample distribution with a configurable target bin count."""

    bins: int = Field(default=20, gt=0)

    def __call__(self, values: np.ndarray) -> go.Figure:
        """Return a histogram for a one-dimensional sample array."""
        return go.Figure(
            go.Histogram(x=values, nbinsx=self.bins),
            layout={
                "title": "Distribution",
                "xaxis_title": "Value",
                "yaxis_title": "Count",
            },
        )


class SignalArtifacts(ArtifactSpec[ArtifactContext]):
    """Two configurable figures with common export settings.

    The collection's format list and exporter apply to both figures. Each figure
    keeps its own construction settings and ``save`` flag.
    """

    signal: SignalViz = Field(default_factory=SignalViz)
    histogram: HistogramViz = Field(default_factory=HistogramViz)
    save_formats: list[PlotlyFigExportFormat] = Field(default=["html"])
    save_plotly: PlotlyFigExport = Field(default_factory=PlotlyFigExport)

    def __call__(self, values: np.ndarray) -> ArtifactContext:
        """Create the figures with their effective export settings."""
        artifacts = ArtifactContext()
        for configured in (self.signal, self.histogram):
            spec = configured.model_copy(
                update={
                    "save_formats": self.save_formats,
                    "save_plotly": self.save_plotly,
                }
            )
            artifacts.add(spec, spec(values))
        return artifacts

    def write(self, data: ArtifactContext, *, path: Path) -> list[ArtifactFile]:
        """Write the retained figures beneath a supplied output directory."""
        files = []
        for name, spec in (("signal", self.signal), ("histogram", self.histogram)):
            artifact = data[spec]
            files.extend(artifact.spec.write(artifact.data, path=path / name))
        return files


class SignalPlotConfig(StepConfig):
    """Signal plot settings with optional eager export and local display."""

    artifacts: SignalArtifacts = Field(default_factory=SignalArtifacts)
    save_path: AnyPath | None = None
    show: bool = False
    show_plotly: PlotlyFigShowInDash = Field(default_factory=PlotlyFigShowInDash)


class SignalPlotContext(StepContext["SignalPlot", SignalPlotConfig]):
    """Plot invocation with receipts for any eagerly written files."""

    files: list[ArtifactFile] = Field(default_factory=list)


class SignalPlot(Step[SignalPlotConfig, SignalPlotContext]):
    """Create diagnostics for the signal variable of a Dataset."""

    @classmethod
    def run(cls, data: xr.Dataset, context: SignalPlotContext) -> None:
        """Retain figures, then perform configured eager export or display."""
        config = context.config
        context.artifacts = config.artifacts(data.signal.values)
        if config.save_path is not None:
            context.files = config.artifacts.write(
                context.artifacts, path=config.save_path
            )
        if config.show:
            config.show_plotly(
                {
                    "Signal": context.artifacts[config.artifacts.signal].data,
                    "Distribution": context.artifacts[config.artifacts.histogram].data,
                },
                title="Signal diagnostics",
            )
