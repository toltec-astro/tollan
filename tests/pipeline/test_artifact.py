"""Typed artifacts and their step/configuration lifetimes."""

import json
import pickle
import subprocess
import sys
from typing import Literal, assert_type

import numpy as np
import plotly.graph_objects as go
import pytest
import xarray as xr

from docs.examples.artifact_example import (
    HistogramViz,
    SignalArtifacts,
    SignalPlot,
    SignalPlotConfig,
    SignalViz,
)
from tollan.pipeline import Artifact, ArtifactContext, ArtifactSpec


class TextSpec(ArtifactSpec[str]):
    def __call__(self, value: int) -> str:
        return str(value)


def test_typed_lookup_aliases_and_replacement():
    default = TextSpec()
    second = TextSpec(alias="second")
    entries = ArtifactContext()
    first = entries.add(default, default(1))
    other = entries.add(second, second(2))

    assert_type(entries[TextSpec], Artifact[str])
    assert_type(entries[second], Artifact[str])
    assert_type(entries.get(TextSpec), Artifact[str] | None)
    assert_type(entries.get(TextSpec, 0), Artifact[str] | Literal[0])
    assert entries[TextSpec] is entries[default] is first
    assert entries[second] is other
    assert entries[TextSpec.get_context_key(alias="second")] is other
    assert set(entries) == {
        TextSpec.get_context_key(),
        TextSpec.get_context_key(alias="second"),
    }
    assert TextSpec in entries
    assert second in entries
    assert int not in entries
    assert entries.get(12) is None
    assert entries.get(HistogramViz, "absent") == "absent"
    with pytest.raises(KeyError):
        _ = entries[HistogramViz]

    replacement = entries.add(default, "replacement")
    assert entries[TextSpec] is replacement
    assert first.data == "1"
    assert len(entries) == 2
    assert ArtifactContext(entries.values())[second] is other


def test_construction_retains_payload_and_effective_spec():
    configured = SignalArtifacts(
        save_formats=["json"], signal=SignalViz(line_width=3.0)
    )
    values = np.array([1.0, 2.0, 3.0])
    artifacts = configured(values)
    artifact = artifacts[SignalViz]
    assert_type(artifact.data, go.Figure)
    assert isinstance(artifact.spec, SignalViz)
    assert artifact.spec.save_formats == ["json"]
    assert artifact.spec.save_plotly is configured.save_plotly
    assert configured.signal.save_formats == ["html"]
    assert artifact.data.data[0].line.width == 3.0
    assert artifacts[configured.signal] is artifact
    retained = ArtifactContext([artifact])
    assert retained[SignalViz].data is artifact.data
    assert retained[SignalViz].spec is artifact.spec


def test_resolved_config_roundtrip_and_invocation_isolation():
    config = SignalPlotConfig(artifacts=SignalArtifacts(save_formats=["json"]))
    restored = SignalPlotConfig.model_validate_json(config.model_dump_json())
    assert restored == config
    assert isinstance(restored.artifacts.signal, SignalViz)
    assert "SignalArtifacts" in SignalPlotConfig.model_json_schema()["$defs"]
    source = xr.Dataset({"signal": ("sample", [1.0, 2.0, 3.0])})
    _, first = SignalPlot(config)(source, return_context=True)
    _, second = SignalPlot(config)(source, return_context=True)
    assert first.artifacts is not second.artifacts
    assert first.artifacts[SignalViz].data is not second.artifacts[SignalViz].data
    assert first.data is None
    assert source.signal.values.tolist() == [1.0, 2.0, 3.0]
    assert list(source.data_vars) == ["signal"]

    record = SignalPlot.dump_context(first)
    assert "artifacts" not in json.loads(record)
    assert json.loads(record)["config"]["artifacts"]["save_formats"] == ["json"]
    reopened = SignalPlot.load_context(record)
    assert reopened.config == config
    assert reopened.completed
    assert not reopened.artifacts


def test_pickle_restores_figures_and_specs_without_running_step(tmp_path):
    source = xr.Dataset({"signal": ("sample", [1.0, 2.0, 3.0])})
    _, context = SignalPlot(artifacts=SignalArtifacts(save_formats=["json"]))(
        source, return_context=True
    )
    process = subprocess.run(  # noqa: S603 -- Fixed code and temporary test path.
        [
            sys.executable,
            "-c",
            """
import pickle, sys
from pathlib import Path
from docs.examples.artifact_example import SignalPlot, SignalViz
SignalPlot.run = lambda *args: sys.exit('unexpected step run')
SignalViz.__call__ = lambda *args: sys.exit('unexpected figure reconstruction')
context = pickle.loads(sys.stdin.buffer.read())
entry = context.artifacts[SignalViz]
files = entry.spec.write(entry.data, path=Path(sys.argv[1]) / 'signal')
print(files[0].path.name)
""",
            str(tmp_path),
        ],
        input=pickle.dumps(context),
        capture_output=True,
        check=True,
    )
    assert process.stdout.decode().strip() == "signal.json"
    assert (tmp_path / "signal.json").is_file()


def test_eager_and_deferred_exports_use_same_effective_specs(tmp_path):
    source = xr.Dataset({"signal": ("sample", [1.0, 2.0, 3.0])})
    _, context = SignalPlot(
        artifacts=SignalArtifacts(save_formats=["json"]), save_path=tmp_path / "eager"
    )(source, return_context=True)
    files = context.config.artifacts.write(
        context.artifacts, path=tmp_path / "deferred"
    )
    assert context.completed
    assert len(files) == len(context.files) == 2
    for eager, deferred in zip(context.files, files, strict=True):
        assert json.loads(eager.path.read_text()) == json.loads(
            deferred.path.read_text()
        )


def test_export_failure_retains_figures_and_records_step_exception(tmp_path):
    occupied = tmp_path / "file"
    occupied.write_text("occupied")
    source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
    with pytest.raises(FileExistsError):
        SignalPlot(save_path=occupied)(source)
    context = SignalPlot.get_context(source)
    assert not context.completed
    assert len(context.failures) == 1
    assert len(context.artifacts) == 2
    assert not context.files
    assert occupied.read_text() == "occupied"
