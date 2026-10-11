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
   :skip: ModelTableAccessor, ModelColumnMapper, ColumnTypeRule, ScalarColumnRule, TimeColumnRule, QuantityColumnRule, SkyCoordColumnRule

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

.. autodata:: tollan.config.types.path.PathType
   :no-value:

   Accepted path checks: ``"file"``, ``"dir"``, or ``"new"``.

.. autofunction:: tollan.config.types.quantity.quantity_field

.. autofunction:: tollan.config.types.quantity.get_physical_type_from_quantity_type

Pipeline
--------

.. automodapi:: tollan.pipeline
   :skip: StepConfig, StepContext, StepFailure

Plotting
--------

.. automodapi:: tollan.plot.mpl

.. automodapi:: tollan.plot.plotly

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

.. automodapi:: tollan.utils.py

.. automodapi:: tollan.utils.slice

.. automodapi:: tollan.utils.sys

.. automodapi:: tollan.utils.table

.. automodapi:: tollan.utils.typer

.. automodapi:: tollan.utils.typing

.. automodapi:: tollan.utils.xarray

.. automodapi:: tollan.utils.yaml
