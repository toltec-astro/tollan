API Reference
=============

Core Package
------------

.. automodapi:: tollan

.. automodapi:: tollan.cli

Data Accessors
--------------

.. automodapi:: tollan.accessor

.. automodapi:: tollan.accessor.netcdf4

.. automodapi:: tollan.accessor.pandas

.. automodapi:: tollan.accessor.pandas.model_table
   :skip: ModelTableAccessor, ModelColumnMapper, ColumnTypeRule, ExplicitColumnRule, ScalarColumnRule, TimeColumnRule, QuantityColumnRule, SkyCoordColumnRule, RecordRuleMapper, Contains

See :ref:`model-table-declarations` for column-mapping fields and rules.

.. automodapi:: tollan.accessor.xarray
   :skip: Analysis

.. autodata:: tollan.accessor.xarray.utils.XarraySourceT
   :no-value:

.. autodata:: tollan.accessor.xarray.utils.XarrayPayloadT
   :no-value:

Configuration System
--------------------

.. automodapi:: tollan.config
   :skip: ConfigSourceFormat, EnvConfig, FrozenBaseModel, RuntimeConfig, RuntimeInfo

.. automodapi:: tollan.config.sources
   :skip: ConfigSourceFormat, ConfigSourceList, DictConfigSource, EnvFileConfigSource, ListConfigSource, YamlConfigSource

See :doc:`models` for configuration fields, defaults, validators, and JSON schemas.

.. automodapi:: tollan.config.types
   :skip: quantity_field

The annotation aliases are described in :doc:`validation-types`.

.. py:type:: tollan.config.types.unit.UnitField

   A unit declaration; see :ref:`unit-declarations`.

.. py:type:: tollan.config.types.unit.AngleUnitField

   An angular unit declaration; see :ref:`unit-declarations`.

.. py:type:: tollan.config.types.unit.PhysicalTypeField

   A physical-type declaration; see :ref:`unit-declarations`.

.. autodata:: tollan.config.types.path.AnyPath
   :no-value:

.. autodata:: tollan.config.types.path.SubPath
   :no-value:

.. autodata:: tollan.config.types.path.SubPathOrRoot
   :no-value:

.. autodata:: tollan.config.types.path.PathType
   :no-value:

   Accepted path checks: ``"file"``, ``"dir"``, or ``"new"``.

.. autofunction:: tollan.config.types.quantity.quantity_field

.. autofunction:: tollan.config.types.quantity.get_physical_type_from_quantity_type

Pipeline
--------

.. automodapi:: tollan.pipeline
   :skip: StepConfig, StepContext, StepFailure, ArtifactSpec

Plotting
--------

.. automodapi:: tollan.plot.mpl

.. automodapi:: tollan.plot.plotly
   :skip: PlotlyViz, PlotlyFigExport, PlotlyFigExportHtml, PlotlyFigExportImage, PlotlyFigShowInDash

See :ref:`artifact-visualization-models` for visualization and export settings.

.. py:type:: PlotlyFigExportFormat

   Supported figure formats: HTML, JSON, PNG, JPG/JPEG, WebP, PDF, and SVG.

.. _database-resources:

Database resources
------------------

.. automodapi:: tollan.db

.. The SQL expressions' inherited constructors and compiler attributes describe
   SQLAlchemy internals. Document the supported timestamp expressions here.

.. autoclass:: tollan.db.func.create_datetime
   :class-doc-from: class

.. autoclass:: tollan.db.func.utcnow()
   :class-doc-from: class

.. automodule:: tollan.db.mapped_types

.. The annotations contain SQLAlchemy objects whose repr includes memory
   addresses. Show the documented column conventions without those values.

.. automappedtype:: tollan.db.mapped_types.Pk
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Uuid
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Label
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Name
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Desc
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Timestamp
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Created_at
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Updated_at
   :no-value:

.. automappedtype:: tollan.db.mapped_types.Timezone
   :no-value:

.. autoclass:: tollan.db.mapped_types.TimestampMixin

.. autofunction:: tollan.db.mapped_types.fk

.. automodule:: tollan.db.orm
   :members:


Utilities
---------

.. automodapi:: tollan.utils.cli

.. automodapi:: tollan.utils.dict

.. automodapi:: tollan.utils.file

.. automodapi:: tollan.utils.fileloc
   :skip: FileLoc, fileloc

.. autofunction:: tollan.utils.fileloc.fileloc

.. autodata:: tollan.utils.fileloc.FileLocUrl
   :no-value:

   A Pydantic URL restricted to ``file``, ``http``, or ``https`` schemes.

.. automodapi:: tollan.utils.fmt

.. automodapi:: tollan.utils.log

.. automodapi:: tollan.utils.np

.. automodapi:: tollan.utils.pandas

.. automodapi:: tollan.utils.py

.. automodapi:: tollan.utils.registry

.. automodapi:: tollan.utils.slice

.. automodapi:: tollan.utils.sys

.. automodapi:: tollan.utils.table

.. automodapi:: tollan.utils.typer

.. automodapi:: tollan.utils.typing

.. automodapi:: tollan.utils.xarray

.. automodapi:: tollan.utils.yaml
