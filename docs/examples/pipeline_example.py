"""Scale a signal in a DataTree and publish it as a netCDF file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, Field

from tollan.accessor import NameMapping, Schema, SubpathMapping
from tollan.accessor.xarray import XarrayAccessorBase, XarrayMapper
from tollan.pipeline import Step, StepConfig, StepContext, StepFailure, StepFailureKind

if TYPE_CHECKING:
    import xarray as xr


@dataclass
class ScaleSchema(Schema):
    """Input and scaled signals in a working tree."""

    raw_path: SubpathMapping = SubpathMapping.path("raw")
    raw_signal: NameMapping = raw_path / NameMapping.var("signal")
    scaled_path: SubpathMapping = SubpathMapping.path("scaled")


class ScaleMapper(XarrayMapper[ScaleSchema]):
    """Locate the input signal and result leaf."""


@dataclass
class SignalSchema(Schema):
    """Signal in a result dataset."""

    signal: NameMapping = NameMapping.var("signal")


class SignalMapper(XarrayMapper[SignalSchema]):
    """Access signals through the example's schema."""


class ScaleView(XarrayAccessorBase[SignalMapper]):
    """Read the scaled signal from a result dataset or leaf."""

    def _validate(self) -> None:
        self.mapper.get_arr(self.data_source, self.mapper.schema.signal)

    @property
    def signal(self) -> xr.DataArray:
        """Scaled signal."""
        return self.mapper.get_arr(self.data_source, self.mapper.schema.signal)


class ScaleConfig(StepConfig):
    """Multiplicative signal scale."""

    factor: float = 2.0


class ScaleContext(StepContext["Scale", ScaleConfig]):
    """Scale invocation and its result view."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: ScaleView | None = Field(default=None, exclude=True)


class Scale(Step[ScaleConfig, ScaleContext]):
    """Install a scaled signal while retaining the input."""

    @classmethod
    def run(cls, data: xr.DataTree, context: ScaleContext) -> None:
        """Scale the input into the result leaf.

        Parameters
        ----------
        data : xarray.DataTree
            Working tree containing the raw signal. Its scaled leaf is replaced.
        context : ScaleContext
            Settings and execution status for this invocation.

        Returns
        -------
        None
            The scaled signal is installed in the working tree and its view is
            published in context.data. Lazy input arrays remain unevaluated.
        """
        mapper = ScaleMapper.from_data_source(data)
        schema = mapper.schema
        signal = mapper.get_arr(data, schema.raw_signal)
        scaled = (signal * context.config.factor).to_dataset()
        data[cast("str", mapper.get_name(schema.scaled_path))] = scaled
        context.data = ScaleView(mapper.get_node(data, schema.scaled_path))


class WriteSignalConfig(StepConfig):
    """Destination for the scaled signal.

    Parameters
    ----------
    path : pathlib.Path
        Output netCDF file. Its parent directory must exist. An existing file
        is overwritten when the result is available.
    """

    path: Path


class WriteSignalData(BaseModel):
    """Published file location."""

    path: Path


class WriteSignalContext(StepContext["WriteSignal", WriteSignalConfig]):
    """Publication result and execution status."""

    data: WriteSignalData | None = None


class WriteSignal(Step[WriteSignalConfig, WriteSignalContext]):
    """Write the scaled signal and publish its file location."""

    @classmethod
    def run(cls, data: xr.DataTree, context: WriteSignalContext) -> None:
        """Write a result dataset and record its location after success.

        Parameters
        ----------
        data : xarray.DataTree
            Working tree whose Scale context publishes the signal to write.
        context : WriteSignalContext
            Destination settings, failures, and publication result.

        Returns
        -------
        None
            The file location is published in context.data after writing. A
            missing Scale context or payload records a missing-input failure
            and leaves the destination untouched.

        Notes
        -----
        Writing evaluates lazy signal arrays. Computation and file errors
        propagate and may leave an incomplete file at the destination.
        """
        result = Scale.get_context(data).data if Scale.has_context(data) else None
        if result is None:
            context.failures.append(
                StepFailure(
                    kind=StepFailureKind.missing_input,
                    message="No scaled signal is available.",
                )
            )
            return
        result.signal.to_dataset().to_netcdf(context.config.path)
        context.data = WriteSignalData(path=context.config.path)
