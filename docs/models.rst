Models and configuration fields
===============================

These references are generated from Pydantic models. Use :doc:`configuration`
to load settings, :doc:`validation-types` to declare validated fields, and
:doc:`analyses` to implement an analysis.

Runtime settings
----------------

.. autopydantic_model:: tollan.config.FrozenBaseModel
   :class-doc-from: class

.. autopydantic_model:: tollan.config.RuntimeConfig
   :class-doc-from: class

.. autopydantic_model:: tollan.config.RuntimeInfo
   :class-doc-from: class

.. autopydantic_model:: tollan.config.EnvConfig
   :class-doc-from: class
   :inherited-members: BaseModel

Configuration sources
---------------------

.. autodoc-pydantic 2.2 cannot resolve the raw Annotated types in three source
   models' summaries. Their field definitions below show the resolved types.


.. autodata:: tollan.config.sources.base.DictConfigT
   :no-value:

.. autodata:: tollan.config.sources.ConfigSource
   :no-value:

.. autoclass:: tollan.config.sources.base.ConfigSourceFormat
   :members:

.. autopydantic_model:: tollan.config.sources.base.ConfigSourceBase
   :class-doc-from: class

.. autopydantic_model:: tollan.config.sources.base.FileConfigSourceBase
   :class-doc-from: class

.. autopydantic_model:: tollan.config.sources.ConfigSourceList
   :model-show-field-summary: False
   :class-doc-from: class

.. autopydantic_model:: tollan.config.sources.DictConfigSource
   :model-show-field-summary: False
   :class-doc-from: class
   :inherited-members: BaseModel

.. autopydantic_model:: tollan.config.sources.YamlConfigSource
   :class-doc-from: class
   :inherited-members: BaseModel

.. autopydantic_model:: tollan.config.sources.EnvFileConfigSource
   :class-doc-from: class
   :inherited-members: BaseModel

.. autopydantic_model:: tollan.config.sources.ListConfigSource
   :model-show-field-summary: False
   :class-doc-from: class
   :inherited-members: BaseModel

.. _pipeline-models:

Analysis and pipeline configuration
-----------------------------------

.. autopydantic_model:: tollan.accessor.xarray.Analysis
   :class-doc-from: class

.. autopydantic_model:: tollan.pipeline.StepConfig
   :class-doc-from: class

.. autopydantic_model:: tollan.pipeline.StepFailure
   :class-doc-from: class

.. autopydantic_model:: tollan.pipeline.StepContext
   :class-doc-from: class
   :model-show-json: False

To describe a concrete context's exported fields, use
``ContextSubclass.model_json_schema(mode="serialization")``. The default
validation schema cannot represent the live producer class in ``step_cls``.
See :doc:`pipelines` for restoring exported contexts and inspecting failures.

.. _artifact-visualization-models:

Artifact and visualization configuration
----------------------------------------

Use :doc:`artifacts` to select data for persistence or exchange, retain its
specifications, and construct or display visualizations.

.. autopydantic_model:: tollan.pipeline.ArtifactSpec
   :class-doc-from: class

.. autopydantic_model:: tollan.plot.VizBase
   :class-doc-from: class

.. autopydantic_model:: tollan.plot.plotly.PlotlyViz
   :class-doc-from: class

.. autopydantic_model:: tollan.plot.plotly.PlotlyFigExport
   :class-doc-from: class
   :special-members: __call__

.. autopydantic_model:: tollan.plot.plotly.PlotlyFigExportHtml
   :class-doc-from: class

.. autopydantic_model:: tollan.plot.plotly.PlotlyFigExportImage
   :class-doc-from: class

.. autopydantic_model:: tollan.plot.plotly.PlotlyFigShowInDash
   :class-doc-from: class
   :special-members: __call__

File locations
--------------

.. autopydantic_model:: tollan.utils.fileloc.FileLoc
   :class-doc-from: class
   :inherited-members: BaseModel

.. _model-table-declarations:

Model-table column declarations
-------------------------------

Use :doc:`model-tables` to project objects, update table rows, and query them.

.. ModelColumnMapper accepts live callable rules, which have no JSON schema.

.. autopydantic_model:: tollan.accessor.pandas.model_table.ModelColumnMapper
   :class-doc-from: class
   :special-members: __call__
   :model-show-json: False

.. autopydantic_model:: tollan.accessor.pandas.model_table.ColumnTypeRule
   :class-doc-from: class
   :special-members: __call__

.. Column declarations may contain live converters, which have no JSON schema.

.. autopydantic_model:: tollan.accessor.pandas.model_table.ExplicitColumnRule
   :class-doc-from: class
   :special-members: __call__
   :model-show-json: False

.. autopydantic_model:: tollan.accessor.pandas.model_table.ScalarColumnRule
   :class-doc-from: class
   :special-members: __call__

.. autopydantic_model:: tollan.accessor.pandas.model_table.TimeColumnRule
   :class-doc-from: class
   :special-members: __call__

.. autopydantic_model:: tollan.accessor.pandas.model_table.QuantityColumnRule
   :class-doc-from: class
   :special-members: __call__

.. autopydantic_model:: tollan.accessor.pandas.model_table.SkyCoordColumnRule
   :class-doc-from: class
   :special-members: __call__
