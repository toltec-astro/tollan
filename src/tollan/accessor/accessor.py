"""Base class for data accessors and views.

Provides a unified pattern for building both xarray accessors and data views
with automatic mapper creation and type detection.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

from tollan.utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)

from .mapper import Mapper

__all__ = ["AccessorBase"]


class AccessorBase[DataSourceT, MapperT: Mapper]:
    """Base class for data accessors and views with generic support.

    This class provides a unified pattern for:
    1. xarray accessors: Create mapper from data_source automatically
    2. Data views: Accept existing mapper and data_source

    The mapper class is auto-detected from the generic type parameter.

    Notes
    -----
    Bind these type parameters when subclassing:

    ``DataSourceT``
        Type of data source, such as xarray.Dataset or pandas.DataFrame.
    ``MapperT``
        Mapper class used for field resolution.
    """

    # Set on concrete subclasses by __init_subclass__; runtime type: type[MapperT].
    _mapper_cls: ClassVar
    _mapper: MapperT
    _data_source: DataSourceT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Derive the mapper class from the origin type variable.

        For intermediate generic classes (with unresolved TypeVars),
        this gracefully returns without setting _mapper_cls.
        """
        super().__init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            AccessorBase,
            MapperT=GenericBindingRequirement("_mapper_cls", Mapper),
        )
        if bindings is not None:
            cls._mapper_cls = bindings["MapperT"]

    def __init__(
        self,
        data_source: DataSourceT,
        mapper: MapperT | None = None,
    ) -> None:
        """Initialize with data source and optional mapper.

        Parameters
        ----------
        data_source : DataSourceT
            Data source to access
        mapper : MapperT, optional
            Field mapper for data access. If not provided, creates one
            using _mapper_cls.from_data_source(data_source).

        Notes
        -----
        Subclasses can override _validate() for custom validation logic.
        """
        self._data_source = data_source

        # Create mapper if not provided
        if mapper is None:
            mapper_cls = cast("type[MapperT]", type(self)._mapper_cls)
            mapper = mapper_cls.from_data_source(data_source)
        self._mapper = mapper

        # Validate after initialization (no-op by default)
        self._validate()

    @property
    def data_source(self) -> DataSourceT:
        """Effective data source exposed by this accessor."""
        return self._data_source

    @property
    def mapper(self) -> MapperT:
        """Field mapper for data access."""
        return self._mapper

    def _validate(self) -> None:
        """Validate data source compatibility.

        Override in subclasses for custom validation logic.
        Base implementation does nothing (no validation).

        Raises
        ------
        ValueError
            If data is not compatible (subclass responsibility)
        """
