Tollan
======

Tollan provides schema-based data access, validated application configuration,
typed pipeline steps, and scientific Python utilities. Start with installation
and the quick start, then choose a guide for your task.

Version: |release|.

Choose a domain
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Domain
     - What you can do
     - Guide
   * - Data access
     - Map names, expose typed views, and store analysis results.
     - :doc:`schema-mapping-accessors`, :doc:`data-adapters`
   * - Configuration
     - Load settings, validate values, and configure components.
     - :doc:`configuration`, :doc:`validation-types`
   * - CLI
     - Add commands, help, logging, and configuration options.
     - :doc:`cli`
   * - Pipelines
     - Run configured steps and inspect execution results.
     - :doc:`pipelines`
   * - Utilities and plotting
     - Work with files, YAML, units, logging, and figures.
     - :doc:`utilities`
   * - Generic classes
     - Bind schemas, mappers, and models to subclasses.
     - :doc:`generic-runtime-bindings`

.. toctree::
   :maxdepth: 1
   :caption: Guides

   readme
   schema-mapping-accessors
   data-adapters
   pipelines
   configuration
   validation-types
   cli
   utilities
   generic-runtime-bindings

.. toctree::
   :maxdepth: 1
   :caption: Reference

   models
   modules

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
