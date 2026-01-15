"""Base class for data accessors and views.

Provides a unified pattern for building both xarray accessors and data views
with automatic mapper creation and type detection.
"""

from __future__ import annotations

from typing import Any, ClassVar

from tollan.utils.typing import ensure_cls_attr_from_type_args

from .mapper import Mapper

__all__ = ["AccessorBase"]


class AccessorBase[DataSourceT, MapperT: Mapper]:
    """Base class for data accessors and views with generic support.

    This class provides a unified pattern for:
    1. xarray accessors: Create mapper from data_source automatically
    2. Data views: Accept existing mapper and data_source

    The mapper class is auto-detected from the generic type parameter.

    Type Parameters
    ---------------
    DataSourceT
        Type of data source (e.g., xr.Dataset, pandas.DataFrame)
    MapperT : Mapper
        Type of mapper used for field resolution
    """

    _mapper_cls: ClassVar[type[MapperT]]  # pyright: ignore[reportGeneralTypeIssues]
    _mapper: MapperT
    _data_source: DataSourceT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-detect mapper class from generic parameter.

        For intermediate generic classes (with unresolved TypeVars),
        this gracefully returns without setting _mapper_cls.
        """
        super().__init_subclass__(**kwargs)
        ensure_cls_attr_from_type_args(
            cls,
            "_mapper_cls",
            max_depth=2,
            bound=Mapper,
        )

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
            mapper = self._mapper_cls.from_data_source(data_source)
        self._mapper = mapper

        # Validate after initialization (no-op by default)
        self._validate()

    @property
    def data_source(self) -> DataSourceT:
        """Data source containing the data."""
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
