"""Attribute projection and column-wise selection on pandas DataFrames."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import MISSING
from datetime import datetime
from enum import Enum
from functools import partial
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    cast,
    overload,
)

import astropy.units as u
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.time.formats import TimeNumeric
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ...config.types import AngleUnitField, PhysicalTypeField, UnitField
from ...config.types.quantity import get_physical_type_from_quantity_type
from ...utils.pandas import query
from ...utils.py import rgetattr
from ...utils.typing import get_annotation_types

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable

__all__ = [
    "ColumnTypeRule",
    "ExplicitColumnRule",
    "ModelColumn",
    "ModelColumnMapper",
    "ModelTableAccessor",
    "QuantityColumnRule",
    "RecordRuleMapper",
    "ScalarColumnRule",
    "SkyCoordColumnRule",
    "TimeColumnRule",
]


class RecordRuleMapper[ValueT]:
    """Map records to the values of their first matching rules.

    Parameters
    ----------
    rules : iterable of (mapping, object)
        Ordered pairs of scalar equality constraints and result values. All
        constraints in a mapping must match. Omitted keys and ellipsis impose
        no constraint. None matches null values, including NaN and pandas.NA,
        but not empty strings. Missing keys cannot satisfy a constraint.
        An empty mapping matches every record. Rules and constraint mappings
        are copied at construction; result objects are retained unchanged.
    default : object
        Result for records that match no rule, unless overridden for a call.

    Examples
    --------
    >>> mapper = RecordRuleMapper(
    ...     [({"status": "ready"}, 1), ({"status": None}, 0)], default=-1
    ... )
    >>> mapper({"status": "ready", "channel": 2})
    1
    >>> mapper({})
    -1
    >>> mapper.map_table(pd.DataFrame({"status": ["ready", None, "other"]}))
    [1, 0, -1]
    """

    def __init__(
        self,
        rules: Iterable[tuple[Mapping[str, Hashable], ValueT]],
        *,
        default: ValueT,
    ) -> None:
        self._rules = tuple((dict(constraints), value) for constraints, value in rules)
        self._default = default

    @overload
    def __call__(self, record: Mapping[str, Any]) -> ValueT: ...

    @overload
    def __call__[DefaultT](
        self, record: Mapping[str, Any], *, default: DefaultT
    ) -> ValueT | DefaultT: ...

    def __call__(self, record: Mapping[str, Any], *, default: Any = MISSING) -> Any:
        """Return the value of the first rule matching a record.

        Parameters
        ----------
        record : mapping of str to scalar
            Named scalar values. Extra keys are ignored. The record is not
            modified; null values match only a None constraint.
        default : object, optional
            Result for an unmatched record in this call. If omitted, use the
            configured default. Explicit None is an override. The mapper's
            configured default is not changed.

        Returns
        -------
        object
            Matching rule value, or the effective default. Result objects,
            including callables and enum members, are returned unchanged.
        """
        for constraints, value in self._rules:
            for name, expected in constraints.items():
                if expected is ...:
                    continue
                if name not in record:
                    break
                actual = record[name]
                if expected is None:
                    matches = pd.isna(actual)
                else:
                    matches = False if pd.isna(actual) else actual == expected
                if matches is pd.NA or not matches:
                    break
            else:
                return value
        return self._default if default is MISSING else default

    @overload
    def map_table(
        self,
        table: pd.DataFrame,
        *,
        column_names: Mapping[str, str] | None = None,
    ) -> list[ValueT]: ...

    @overload
    def map_table[DefaultT](
        self,
        table: pd.DataFrame,
        *,
        column_names: Mapping[str, str] | None = None,
        default: DefaultT,
    ) -> list[ValueT | DefaultT]: ...

    def map_table(
        self,
        table: pd.DataFrame,
        *,
        column_names: Mapping[str, str] | None = None,
        default: Any = MISSING,
    ) -> list[Any]:
        """Return one rule value per table row using column-wise matching.

        Parameters
        ----------
        table : pandas.DataFrame
            Scalar input columns. The table is not modified. Missing columns
            cannot satisfy a constraint; nulls match only a None constraint.
        column_names : mapping of str to str, optional
            Rule field names mapped to input column names. Unmapped names are
            used unchanged. If omitted, rule names are table column names.
        default : object, optional
            Result for unmatched rows in this call. If omitted, use the
            configured default. Explicit None is an override. The mapper's
            configured default is not changed.

        Returns
        -------
        list
            First matching rule values, or the effective default, in row
            order regardless of index labels. Result objects are unchanged.
            Assign this list to a column to update the table in place.

        Notes
        -----
        This is an optimized batch equivalent of evaluating each record.
        Constraints are evaluated column-wise and repeated comparisons are
        reused, avoiding a Python-level loop over records. For a fixed rule
        set, runtime remains linear in the number of rows.
        """
        values = np.empty(len(self._rules) + 1, dtype=object)
        values[-1] = self._default if default is MISSING else default
        selected = np.full(len(table), -1, dtype=np.intp)
        unmatched = np.ones(len(table), dtype=bool)
        names = {} if column_names is None else column_names
        comparisons = {}
        for i, (constraints, value) in enumerate(self._rules):
            if not unmatched.any():
                break
            values[i] = value
            matches = unmatched.copy()
            for attr, expected in constraints.items():
                if expected is ...:
                    continue
                name = names.get(attr, attr)
                if name not in table:
                    matches[:] = False
                    break
                key = (name, expected)
                if key not in comparisons:
                    column = table[name]
                    comparisons[key] = (
                        column.isna()
                        if expected is None
                        else column.eq(cast("Any", expected))
                    ).to_numpy(dtype=bool, na_value=False)
                matches &= comparisons[key]
            selected[matches] = i
            unmatched &= ~matches
        return values[selected].tolist()


class ModelColumn(NamedTuple):
    """A table column read from a dotted model attribute.

    Parameters
    ----------
    attr : str
        Attribute path to read, with dots separating nested attributes.
    default : object, optional
        Value used when the attribute is missing. If omitted, a missing
        attribute raises AttributeError. This does not fill untouched table rows.
    dtype : pandas dtype, optional
        Projected column dtype. Default is object dtype. When updating an
        existing column, its dtype is retained rather than replaced by this one.
    converter : callable, optional
        Function applied to non-None values, including a non-None default.
        None is preserved. If omitted, values are used unchanged.
    """

    attr: str
    default: Any = MISSING
    dtype: Any = None
    converter: Callable[[Any], Any] | None = None

    def read(self, model: object) -> Any:
        """Read and convert a column value.

        Parameters
        ----------
        model : object
            Object from which to read the configured attribute path.

        Returns
        -------
        object
            Converted attribute value, or the configured fallback.

        Raises
        ------
        AttributeError
            If the attribute is missing and no default is configured.
        """
        value = (
            rgetattr(model, self.attr)
            if self.default is MISSING
            else rgetattr(model, self.attr, self.default)
        )
        if value is None or self.converter is None:
            return value
        return self.converter(value)


def _enum_value(value):
    return value.value if isinstance(value, Enum) else value


def _quantity_value(value, *, unit):
    if not value.isscalar:
        msg = "A quantity column requires scalar values"
        raise ValueError(msg)
    return value.to_value(unit)


def _time_value(value, *, format):
    if not value.isscalar:
        msg = "A time column requires scalar values"
        raise ValueError(msg)
    return value.to_value(format)


def _coordinate_value(value, *, attr, unit):
    return _quantity_value(getattr(value, attr), unit=unit)


class ColumnTypeRule(BaseModel, ABC):
    """Base class for rules that declare columns from model fields."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )

    @abstractmethod
    def __call__(
        self, name: str, annotation: Any, column_name: str
    ) -> dict[str, ModelColumn] | None:
        """Declare columns for a matching field.

        Parameters
        ----------
        name : str
            Model attribute name.
        annotation : object
            Field's type annotation, including any Annotated metadata.
        column_name : str
            Column name supplied by a name rule.

        Returns
        -------
        dict of str to ModelColumn or None
            Column declarations, or None if the field does not match.
            An empty dict matches without producing columns. No model values
            are read.
        """


class ExplicitColumnRule(ColumnTypeRule):
    r"""Project named fields with explicit column declarations.

    Parameters
    ----------
    columns : dict of str to ModelColumn
        Original model field names mapped to column declarations. Matching is
        exact and independent of the field annotation. Each declaration uses
        the output alias supplied by the mapper's name rules. Fields absent
        from this mapping are left to later rules.

    Notes
    -----
    Place this rule before annotation-based rules to override their handling
    of the listed fields. The mapper applies its model_path and default to
    these declarations, as it does for other rules.

    Examples
    --------
    >>> class Entry(BaseModel):
    ...     tags: list[str]
    >>> columns = ModelColumnMapper(
    ...     name_rules=[(r".+", r"item_\g<0>")],
    ...     type_rules=[ExplicitColumnRule(columns={
    ...         "tags": ModelColumn("tags", dtype=object, converter=list),
    ...     })],
    ... )(Entry)
    >>> columns["item_tags"].read(Entry(tags=["ready"]))
    ['ready']
    """

    columns: dict[str, ModelColumn]

    def __call__(self, name, annotation, column_name):
        """Declare a column for a listed field.

        See Also
        --------
        ColumnTypeRule.__call__ : Rule arguments and return convention.
        """
        if name not in self.columns:
            return None
        return {column_name: self.columns[name]}


class TimeColumnRule(ColumnTypeRule):
    """Project scalar Time values in the selected format, preserving time scale.

    Parameters
    ----------
    format : str
        Astropy Time output format. Appended to the column name as a suffix,
        for example ``_mjd``.
    """

    format: str

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value):
        if value not in Time.FORMATS:
            msg = f"Unknown time format {value!r}"
            raise ValueError(msg)
        return value

    def __call__(self, name, annotation, column_name):
        """Declare a column for a matching time annotation.

        See Also
        --------
        ColumnTypeRule.__call__ : Rule arguments and return convention.
        """
        if get_annotation_types(annotation) - {type(None)} != {Time}:
            return None
        dtype = (
            "Float64" if issubclass(Time.FORMATS[self.format], TimeNumeric) else None
        )
        return {
            f"{column_name}_{self.format}": ModelColumn(
                name, dtype=dtype, converter=partial(_time_value, format=self.format)
            )
        }


class SkyCoordColumnRule(ColumnTypeRule):
    """Project angular coordinate attributes and their frame name.

    Parameters
    ----------
    attrs : sequence of str
        Distinct angular attributes to read, for example ``["ra", "dec"]``.
        At least one is required. A missing attribute raises AttributeError
        when reading a coordinate.
    unit : str or astropy.units.UnitBase
        Angular output unit. Column names gain attribute and unit suffixes;
        ``attrs=["l", "b"], unit="deg"`` produces ``_l_deg`` and ``_b_deg``.

    Notes
    -----
    The accompanying ``_frame`` column contains the coordinate's Astropy frame
    name, such as ``"icrs"`` or ``"galactic"``. Coordinates are not transformed.
    """

    # Accept sequence declarations while validating each attribute strictly.
    attrs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1, strict=False
    )
    unit: AngleUnitField

    @field_validator("attrs")
    @classmethod
    def _validate_attrs(cls, value):
        if len(value) != len(set(value)):
            msg = "Coordinate attributes must be unique"
            raise ValueError(msg)
        return value

    def __call__(self, name, annotation, column_name):
        """Declare angular and frame columns for a coordinate annotation.

        See Also
        --------
        ColumnTypeRule.__call__ : Rule arguments and return convention.
        """
        if get_annotation_types(annotation) - {type(None)} != {SkyCoord}:
            return None
        return {
            f"{column_name}_{attr}_{self.unit}": ModelColumn(
                name,
                dtype="Float64",
                converter=partial(_coordinate_value, attr=attr, unit=self.unit),
            )
            for attr in self.attrs
        } | {
            f"{column_name}_frame": ModelColumn(
                name, dtype="string", converter=partial(rgetattr, attr="frame.name")
            )
        }


class QuantityColumnRule(ColumnTypeRule):
    """Project quantities annotated with one physical type into a selected unit.

    Parameters
    ----------
    physical_type : str or astropy.units.PhysicalType
        Physical type required by the quantity annotation. Unconstrained
        quantities and annotations allowing several physical types do not match.
    unit : str or astropy.units.UnitBase
        Compatible output unit. Appended to the column name as a suffix,
        for example ``_s`` or ``_Hz``.
    """

    physical_type: PhysicalTypeField
    unit: UnitField

    @model_validator(mode="after")
    def _validate_unit(self):
        if self.unit.physical_type != self.physical_type:
            msg = (
                f"Unit {self.unit!s} does not have physical type {self.physical_type!s}"
            )
            raise ValueError(msg)
        return self

    def __call__(self, name, annotation, column_name):
        """Declare a quantity column with the configured physical type and unit.

        See Also
        --------
        ColumnTypeRule.__call__ : Rule arguments and return convention.
        """
        if get_annotation_types(annotation) - {type(None)} != {u.Quantity}:
            return None
        if get_physical_type_from_quantity_type(annotation) != self.physical_type:
            return None
        return {
            f"{column_name}_{self.unit}": ModelColumn(
                name,
                dtype="Float64",
                converter=partial(_quantity_value, unit=self.unit),
            )
        }


class ScalarColumnRule(ColumnTypeRule):
    """Project primitive scalars and enum values without changing column names.

    Nullable homogeneous types use their pandas extension dtype. Mixed scalar
    unions use object dtype; containers and nested models do not match.
    """

    def __call__(self, name, annotation, column_name):
        """Declare a column for a scalar annotation.

        See Also
        --------
        ColumnTypeRule.__call__ : Rule arguments and return convention.
        """
        types = get_annotation_types(annotation) - {type(None)}
        enums = {
            item for item in types if isinstance(item, type) and issubclass(item, Enum)
        }
        value_types = (types - enums) | {
            type(member.value) for enum in enums for member in enum.__members__.values()
        }
        dtypes = {bool: "boolean", int: "Int64", float: "Float64", str: "string"}
        if value_types == {AwareDatetime}:
            dtype = "datetime64[ns, UTC]"
        elif value_types <= {bool, int, float, str, bytes, datetime}:
            dtype = (
                dtypes.get(next(iter(value_types))) if len(value_types) == 1 else None
            )
        else:
            return None
        return {column_name: ModelColumn(name, dtype=dtype, converter=_enum_value)}


class ModelColumnMapper(BaseModel):
    r"""Declare table columns using ordered name and type rules.

    Parameters
    ----------
    name_rules : sequence of (regex, replacement) pairs
        Full-match patterns for model field names and their column-name
        replacements. All matching rules apply; duplicate aliases are removed
        in declaration order. Replacements accept regular-expression
        backreferences, such as ``r"file_\g<0>"``. Unmatched fields are skipped.
    type_rules : sequence of callable
        Rules accepting ``(name, annotation, column_name)``; see `ColumnTypeRule`.
        For each alias, the first matching rule supplies its final columns.
        Repeated callables and identically configured rule models are rejected.
        An empty name-rule or type-rule list produces no columns.
    exclude : str or compiled regex, optional
        Full-match pattern for field names to omit, before applying name rules.
        Default is no exclusion.
    include_computed : bool, optional
        Whether to include Pydantic computed fields. Default is False.
    model_path : str, optional
        Dotted attribute path locating the model in an input object, for example
        ``"metadata"``. Does not affect field-name matching. Default is None,
        meaning attributes are read directly from the input object.
    default : object, optional
        Fallback for missing attributes in the generated columns. If omitted,
        missing attributes raise AttributeError when reading values.

    Notes
    -----
    Generate declarations once per desired projection and reuse the returned
    mapping across batches. Each call generates declarations again without
    reading object values. The mapping can read objects of different classes
    that provide the declared attributes.

    Examples
    --------
    >>> class Reading(BaseModel):
    ...     value: int
    >>> columns = ModelColumnMapper(
    ...     name_rules=[(r".+", r"sample_\g<0>")],
    ...     type_rules=[ScalarColumnRule()],
    ... )(Reading)
    >>> columns["sample_value"].read(Reading(value=3))
    3
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )

    # Rule declarations accept lists as well as tuples; their values remain strict.
    name_rules: tuple[
        Annotated[tuple[re.Pattern[str], str], Field(strict=False)], ...
    ] = Field(strict=False)
    type_rules: tuple[Callable[[str, Any, str], dict[str, ModelColumn] | None], ...] = (
        Field(strict=False)
    )
    exclude: re.Pattern[str] | None = None
    include_computed: bool = False
    model_path: Annotated[str, Field(pattern=r"^[^.]+(?:\.[^.]+)*$")] | None = None
    default: Any = Field(default_factory=lambda: MISSING)

    @field_validator("name_rules")
    @classmethod
    def _validate_name_rules(cls, value):
        for pattern, replacement in value:
            try:
                # re.sub validates backreferences even without a matching name.
                pattern.sub(replacement, "")
            except (re.error, IndexError) as error:
                raise ValueError(str(error)) from error
        return value

    @field_validator("type_rules")
    @classmethod
    def _validate_type_rules(cls, value):
        for index, rule in enumerate(value):
            for previous_index, previous in enumerate(value[:index]):
                if rule is previous or (
                    isinstance(rule, ColumnTypeRule)
                    and isinstance(previous, ColumnTypeRule)
                    and rule == previous
                ):
                    msg = (
                        f"Duplicate type rules at indices {previous_index} and {index}"
                    )
                    raise ValueError(msg)
        return value

    def _map_name(self, name: str) -> tuple[str, ...]:
        if self.exclude is not None and self.exclude.fullmatch(name) is not None:
            return ()
        return tuple(
            dict.fromkeys(
                match.expand(replacement)
                for pattern, replacement in self.name_rules
                if (match := pattern.fullmatch(name)) is not None
            )
        )

    def _map_type(
        self, name: str, annotation: Any, column_name: str
    ) -> dict[str, ModelColumn] | None:
        for rule in self.type_rules:
            mapped = rule(name, annotation, column_name)
            if mapped is not None:
                return mapped
        return None

    def __call__(
        self,
        model_cls: type[BaseModel],
        **updates: Any,
    ) -> dict[str, ModelColumn]:
        """Create columns without evaluating model values.

        Parameters
        ----------
        model_cls : type of pydantic.BaseModel
            Model whose field annotations determine the columns. Serialization
            aliases and exclusions do not affect projection.
        **updates
            Validated replacements for mapper settings, for this call only.
            This mapper is not modified.

        Returns
        -------
        dict of str to ModelColumn
            Column declarations. Explicit entries can be added or overridden
            with the dict ``|`` operator. Overriding replaces a declaration;
            it does not retain alternative readers for the same column.

        Raises
        ------
        ValueError
            If multiple projections produce the same final column name.
        """
        if updates:
            # model_copy(update=...) does not validate replacement settings.
            # dict(self) also preserves an arbitrary default object as-is.
            mapper = type(self).model_validate(dict(self) | updates)
            return mapper(model_cls)

        # Pydantic separates outer Annotated metadata from the field annotation.
        annotations = {
            name: Annotated[info.annotation, *info.metadata]
            if info.metadata
            else info.annotation
            for name, info in model_cls.model_fields.items()
        }
        if self.include_computed:
            annotations |= {
                name: info.return_type
                for name, info in model_cls.model_computed_fields.items()
            }
        columns = {}
        for name, annotation in annotations.items():
            for column_name_base in self._map_name(name):
                mapped = self._map_type(name, annotation, column_name_base)
                if mapped is None:
                    continue
                for column_name, column in mapped.items():
                    if column_name in columns:
                        msg = (
                            f"Column name {column_name!r} is produced by "
                            "multiple projections"
                        )
                        raise ValueError(msg)
                    columns[column_name] = column._replace(
                        attr=column.attr
                        if self.model_path is None
                        else f"{self.model_path}.{column.attr}",
                        default=self.default,
                    )
        return columns


class ModelTableAccessor:
    """Project objects into flat tables for selection and enrichment.

    Parameters
    ----------
    data : pandas.DataFrame
        Table to access. Construction neither copies nor validates the frame.

    Examples
    --------
    >>> class Measurement(BaseModel):
    ...     channel: int
    ...     amplitude: float
    >>> table = ModelTableAccessor.from_models([
    ...     Measurement(channel=1, amplitude=2.5),
    ...     Measurement(channel=2, amplitude=0.5),
    ... ], columns={
    ...     "channel": ModelColumn("channel", dtype="Int64"),
    ...     "amplitude": ModelColumn("amplitude", dtype="Float64"),
    ... })
    >>> selected = ModelTableAccessor(table).query("amplitude > 1")
    >>> next(selected.itertuples(index=False)).channel
    np.int64(1)
    """

    _query_namespace: ClassVar[dict[str, object]] = {}

    def __init__(self, data: pd.DataFrame) -> None:
        self._obj = data

    @classmethod
    def from_models(
        cls,
        models: Iterable[object],
        *,
        columns: Mapping[str, ModelColumn],
    ) -> pd.DataFrame:
        """Build a flat table from declared attribute paths.

        Parameters
        ----------
        models : iterable of object
            Objects to project, one per output row. They need not share a type;
            only the declared attribute paths are read.
        columns : mapping of str to ModelColumn
            Output column names and their attribute paths, defaults, converters
            and dtypes. The same projection is applied to every input object;
            mappings are not selected by object type.

        Returns
        -------
        pandas.DataFrame
            Projected values in input order. Empty input retains the declared
            columns and dtypes.

        Raises
        ------
        AttributeError
            If a required attribute is missing and no fallback is declared.
        """
        readers = tuple(column.read for column in columns.values())
        rows = ([read(model) for read in readers] for model in models)
        # Preserve native values and large nullable integers before dtype conversion.
        table = pd.DataFrame(rows, columns=list(columns), dtype=object)
        dtypes = {
            name: column.dtype
            for name, column in columns.items()
            if column.dtype is not None
        }
        return table.astype(dtypes) if dtypes else table

    @overload
    def update_from_models(
        self,
        models: Iterable[object] | Mapping[int, object],
        *,
        columns: Mapping[str, ModelColumn],
        inplace: Literal[False] = False,
    ) -> pd.DataFrame: ...

    @overload
    def update_from_models(
        self,
        models: Iterable[object] | Mapping[int, object],
        *,
        columns: Mapping[str, ModelColumn],
        inplace: Literal[True],
    ) -> None: ...

    @overload
    def update_from_models(
        self,
        models: Iterable[object] | Mapping[int, object],
        *,
        columns: Mapping[str, ModelColumn],
        inplace: bool,
    ) -> pd.DataFrame | None: ...

    def update_from_models(
        self,
        models: Iterable[object] | Mapping[int, object],
        *,
        columns: Mapping[str, ModelColumn],
        inplace: bool = False,
    ) -> pd.DataFrame | None:
        """Project objects into existing table rows.

        Parameters
        ----------
        models : iterable of object or mapping of int to object
            An iterable with exactly one object per table row, or a mapping
            from integer row positions to objects. Positions follow ``iloc``
            conventions, including negative positions. Slices and broadcasting
            are not supported.
        columns : mapping of str to ModelColumn
            Columns to update and their projections. Null values overwrite
            existing values, including null defaults for missing attributes.
            Omitted columns remain unchanged. Values are projected using the
            declared dtypes before assignment. Existing column dtypes are
            retained; incompatible assignments raise. New columns use the
            declared dtypes, which must support missing values for untouched
            rows. Those rows are not filled from ModelColumn.default.
        inplace : bool, optional
            Whether to update this table. Default is False.

        Returns
        -------
        pandas.DataFrame or None
            Updated table, or None if ``inplace=True``. Other rows and columns,
            the index and table attributes are preserved.

        Raises
        ------
        ValueError
            If an iterable has the wrong length, or mapping keys identify the
            same row after resolving negative positions.
        TypeError
            If a mapping key is not an integer row position.
        IndexError
            If a row position is out of bounds.

        Notes
        -----
        Separate calls may populate the same column from different attribute
        paths and converters. Reuse each projection for batches of compatible
        objects; its readers need not match those used in earlier calls.

        Duplicate index labels are supported because updates use row positions.
        In-place updates are not transactional: an assignment error may leave
        earlier columns updated.
        """
        row_range = range(len(self._obj))
        if isinstance(models, Mapping):
            models_resolved = {}
            for position, model in models.items():
                if not pd.api.types.is_integer(position):
                    msg = "Update mapping keys must be integer row positions"
                    raise TypeError(msg)
                models_resolved[row_range[position]] = model
            if len(models_resolved) != len(models):
                msg = "Updated row positions must identify distinct rows"
                raise ValueError(msg)
            if not models_resolved:
                return None if inplace else self._obj.copy()
            rows = list(models_resolved)
            models = models_resolved.values()
        else:
            models = list(models)
            if len(models) != len(row_range):
                msg = (
                    "Provide one object per table row, or a position-to-object mapping"
                )
                raise ValueError(msg)
            rows = list(row_range)
        projected = self.from_models(models, columns=columns)
        result = self._obj if inplace else self._obj.copy()
        column_positions = result.columns.get_indexer(projected.columns).tolist()
        for (name, values), position in zip(
            projected.items(), column_positions, strict=True
        ):
            if position >= 0:
                result.iloc[rows, position] = values.array
            else:
                column = pd.Series(None, index=result.index, dtype=values.dtype)
                column.iloc[rows] = values.array
                result[name] = column.array
        return None if inplace else result

    def query(self, expression: str) -> pd.DataFrame:
        """Select rows using pandas expressions on the table columns.

        Parameters
        ----------
        expression : str
            Pandas query expression evaluated with the Python engine.
            Only use trusted expressions. Column names take precedence over
            query functions and constants.

        Returns
        -------
        pandas.DataFrame
            Selected rows, preserving their index labels.

        See Also
        --------
        tollan.utils.pandas.query : Standalone query with the same helpers.
        """
        return query(self._obj, expression, namespace=self._get_query_namespace())

    def _get_query_namespace(self) -> dict[str, object]:
        """Names available to query expressions alongside table columns."""
        return self._query_namespace
