"""Pipeline step base classes.

Provides typed steps over containers with an ``.attrs`` or ``.meta`` mapping:

- Context is stored in ``data.attrs["__pipeline_context__"]`` or the corresponding
  entry in ``data.meta`` when ``attrs`` is absent.
- :class:`Step` subclasses declare typed :class:`StepConfig` /
  :class:`StepContext` type-variable bindings; ``Step.get_context(data)`` returns
  the typed context without dict-key lookups at the call site.
- :class:`SequentialPipeline` executes a list of steps in order, skipping
  disabled ones.

Store scientific products in the working container and publish what downstream
steps need through a typed ``context.data`` field. This can be a view of those
products or a bundle of views, arrays, tables, figures, and file locations.
Leave it as None when the step does not need to publish a payload.

Use ``Step.dump_context()`` to obtain JSON for export. The product writer selects
which contexts to save and where to store the returned strings. Read saved values
through the producing step's ``load_context()``; excluded live payloads are not
reconstructed.

Examples
--------
Install a result variable while preserving the input variable. This minimal
step leaves ``context.data`` as None; the pipeline guide demonstrates publishing
a typed result view for downstream steps.

>>> import xarray as xr
>>> class ScaleConfig(StepConfig):
...     factor: float = 2.0
>>> class ScaleContext(StepContext["Scale", ScaleConfig]):
...     pass
>>> class Scale(Step[ScaleConfig, ScaleContext]):
...     @classmethod
...     def run(cls, data, context):
...         data["scaled"] = data["signal"] * context.config.factor
>>> source = xr.Dataset({"signal": ("sample", [1.0, 2.0])})
>>> Scale(factor=3.0)(source) is source
True
>>> source["signal"].values.tolist(), source["scaled"].values.tolist()
([1.0, 2.0], [3.0, 6.0])
>>> context = Scale.get_context(source)
>>> source.attrs[PIPELINE_CONTEXT_KEY][Scale] is context
True
>>> context.completed, context.data, context.config.factor
(True, None, 3.0)
"""

from __future__ import annotations

import json
from collections import UserDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import (
    Any,
    ClassVar,
    Literal,
    TypeVar,
    cast,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..utils.log import logger, timeit
from ..utils.py import getname
from ..utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)

__all__ = [
    "PIPELINE_CONTEXT_KEY",
    "Pipeline",
    "SequentialPipeline",
    "Step",
    "StepConfig",
    "StepContext",
    "StepContextDict",
    "StepFailure",
    "StepFailureKind",
    "get_pipeline_contexts",
]

ConfigT = TypeVar("ConfigT", bound="StepConfig")
ContextT = TypeVar("ContextT", bound="StepContext")
StepT = TypeVar("StepT", bound="Step")

PIPELINE_CONTEXT_KEY: Literal["__pipeline_context__"] = "__pipeline_context__"


# ---------------------------------------------------------------------------
# Config and context base models
# ---------------------------------------------------------------------------


class StepConfig(BaseModel):
    """Base pydantic model for pipeline step configuration.

    Subclasses add domain-specific config fields.  The ``enabled`` flag
    is honoured by :class:`SequentialPipeline` to skip disabled steps. Set
    ``alias`` to keep separate invocation contexts for repeated steps.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True, description="Set False to skip this step in a SequentialPipeline."
    )
    alias: str | None = Field(
        default=None,
        description=(
            "Invocation label for a separate context; "
            "None selects the primary operation."
        ),
    )


class StepFailureKind(StrEnum):
    """Categories of failures encountered during an operation."""

    #: A required input or prior result is unavailable.
    missing_input = auto()
    #: An available input cannot be used by this operation.
    invalid_input = auto()
    #: An Exception escaped the step's run method.
    exception = auto()
    #: A failure described by its message and details.
    other = auto()


class StepFailure(BaseModel):
    """Failure encountered during an operation.

    Append instances to ``context.failures`` as failures occur. Use ``kind`` to
    group failures and ``details`` for information specific to the operation.

    Parameters
    ----------
    message : str
        Description of the failure.
    kind : StepFailureKind, optional
        Failure category. Defaults to other.
    exception_type : str, optional
        Exception class name, or None for a failure reported without raising.
    details : dict of str to JSON values, optional
        Additional information such as an input name or channel. Defaults to an
        empty mapping.
    """

    message: str = Field(description="Description of the failure.")
    kind: StepFailureKind = Field(
        default=StepFailureKind.other, description="Category of the failure."
    )
    exception_type: str | None = Field(
        default=None, description="Escaping exception's class name, when applicable."
    )
    details: dict[str, JsonValue] = Field(
        default_factory=dict, description="Operation-specific JSON-compatible details."
    )


class StepContext[StepT: "Step", ConfigT: "StepConfig"](BaseModel):
    """Results and execution status for one step invocation.

    :meth:`Step.create_context` attaches a fresh context to the working container
    before each run. Subclasses can publish typed results through ``data``;
    fields need defaults so the context can exist before results are available.
    A payload can contain views of products in the working container and other
    objects needed by downstream steps.

    Parameters
    ----------
    step_cls : type of Step
        Producing step class. Excluded from model dumps; restore exported fields
        through that producer's :meth:`Step.load_context`.
    config : StepConfig
        Settings used for this invocation, including its alias.
    data : None, optional
        Published results or views. Subclasses specify the payload type and its
        initial value. Defaults to None when no payload is needed.
    completed : bool, optional
        Initially False. The step sets True after a normal return with no failures.
        Lazy results may still require computation.
    failures : list of StepFailure, optional
        Failures in append order; each invocation starts with an empty list.

    Notes
    -----
    An ``Exception`` escaping ``run()`` adds its message and class name to
    ``failures`` before being re-raised. Completion describes this invocation;
    it does not establish that stored results are fresh for later input data.
    Deferred computation errors are recorded by the step that evaluates the
    results. Evaluating them outside a step does not update invocation contexts.
    """

    step_cls: type[Any] = Field(
        exclude=True, repr=False, description="Concrete step class for this invocation."
    )

    config: ConfigT
    data: None = None
    completed: bool = False
    failures: list[StepFailure] = Field(
        default_factory=list, description="Failures encountered during this invocation."
    )

    @property
    def config_cls(self) -> type[StepConfig]:
        """Configuration model of the producing step."""
        return self.step_cls.config_cls

    def make_step(self) -> StepT:
        """Reconstruct the producing step with this invocation's settings.

        Returns
        -------
        Step
            New instance of ``step_cls``, retaining the saved configuration and
            alias. Reconstructing a step does not run it or restore input data.
        """
        return cast("StepT", self.step_cls(self.config))


# ---------------------------------------------------------------------------
# Context dict
# ---------------------------------------------------------------------------


class StepContextDict(UserDict[str, StepContext]):
    """Mapping from step context-key → :class:`StepContext`.

    Acts as the pipeline's in-memory context store, keyed by the step's
    :attr:`Step.context_key`.  Supports key resolution from a step class,
    step instance, callable, or plain string.
    """

    @classmethod
    def resolve_key(cls, arg: Any) -> str:
        """Return the string context key for *arg*.

        Parameters
        ----------
        arg : Any
            A :class:`Step` subclass, :class:`Step` instance, callable, or str.

        Returns
        -------
        str
            The context key string. An instance includes its configured alias;
            a class selects the primary invocation.

        Raises
        ------
        TypeError
            The argument is neither a supported key nor a named callable.
        """
        if isinstance(arg, str):
            return arg
        if isinstance(arg, type) and issubclass(arg, Step):
            return arg.context_key
        if isinstance(arg, Step):
            return arg.context_key
        if callable(arg):
            return getname(arg)
        msg = f"invalid step context key arg: {arg!r}"
        raise TypeError(msg)

    def __setitem__(self, key: Any, item: StepContext) -> None:
        super().__setitem__(self.resolve_key(key), item)

    def __getitem__(self, key: Any) -> StepContext:
        return super().__getitem__(self.resolve_key(key))

    def __contains__(self, key: Any) -> bool:  # type: ignore[override]
        try:
            return super().__contains__(self.resolve_key(key))
        except TypeError:
            return False


# ---------------------------------------------------------------------------
# Pipeline context store accessor
# ---------------------------------------------------------------------------


def get_pipeline_contexts(data: Any) -> StepContextDict:
    """Return the :class:`StepContextDict` attached to *data*.

    Looks in ``data.attrs`` (``xr.DataTree`` / ``xr.Dataset``) first, then
    falls back to ``data.meta`` for legacy containers.  Creates an empty
    :class:`StepContextDict` on first access.

    Parameters
    ----------
    data : Any
        Data container — must have ``.attrs`` or ``.meta``.

    Returns
    -------
    StepContextDict
        The pipeline context dict for *data*.

    Raises
    ------
    TypeError
        If *data* has neither ``.attrs`` nor ``.meta``.
    """
    if hasattr(data, "attrs"):
        store = data.attrs
    elif hasattr(data, "meta"):
        store = data.meta
    else:
        msg = f"data of type {type(data).__name__!r} has no .attrs or .meta dict"
        raise TypeError(
            msg,
        )
    if PIPELINE_CONTEXT_KEY not in store:
        store[PIPELINE_CONTEXT_KEY] = StepContextDict()
    return store[PIPELINE_CONTEXT_KEY]


# ---------------------------------------------------------------------------
# context_key descriptor
# ---------------------------------------------------------------------------


class _ContextKeyDescriptor:
    """Non-data descriptor that returns the context key string.

    Works on both the class (``SweepCheck.context_key``) and instances
    (``step_instance.context_key``) without requiring ``@classproperty``.
    Instance access includes the configured alias; class access selects the primary key.
    """

    def __get__(self, obj: Any, cls: type[Step] | None = None) -> str:
        if cls is None:
            cls = type(obj)
        alias = obj.config.alias if obj is not None else None
        return cls.get_context_key(alias=alias)


# ---------------------------------------------------------------------------
# Step base class
# ---------------------------------------------------------------------------


class Step[ConfigT: "StepConfig", ContextT: "StepContext"]:
    """Base class for a typed, context-aware pipeline step.

    Subclasses bind their config and context types through the generic base::

        class MyStep(Step[MyConfig, MyContext]):
            @classmethod
            def run(cls, data, context):
                ...

    The step instance holds its config.  Calling the step on *data*:

    1. Creates a :class:`StepContext` in the container's attrs or meta mapping.
    2. Calls :meth:`run`.
    3. Marks the context complete when ``run()`` finishes without failures.

    Cross-step access is typed::

        ctx = OtherStep.get_context(data)   # returns OtherStepContext
        ctx.data.my_table                   # typed, no dict key needed

    Parameters
    ----------
    *args
        Optional single instance of the bound configuration model.
    **kwargs
        Configuration fields to validate, overriding a supplied model's values.

    Raises
    ------
    ValueError
        More than one positional argument is supplied, or it is not an instance
        of the bound configuration model.
    pydantic.ValidationError
        Configuration fields fail validation.
    """

    config_cls: ClassVar[type[StepConfig]]
    context_cls: ClassVar[type[StepContext]]

    #: Context-store key: the instance's alias, or the primary invocation on a class.
    context_key = _ContextKeyDescriptor()

    _config: ConfigT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls,
            Step,
            ConfigT=GenericBindingRequirement("config_cls", StepConfig),
            ContextT=GenericBindingRequirement("context_cls", StepContext),
        )
        if bindings is None:
            return
        config_cls = bindings["ConfigT"]
        context_cls = bindings["ContextT"]
        context_config_cls = context_cls.model_fields["config"].annotation
        if context_config_cls is not config_cls:
            msg = (
                f"{cls.__name__} binds ConfigT to {config_cls.__name__}, but "
                f"{context_cls.__name__}.config uses {context_config_cls!r}"
            )
            raise TypeError(msg)

        cls.config_cls = config_cls
        cls.context_cls = context_cls

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not args:
            config = self.config_cls.model_validate(kwargs)
        elif len(args) == 1:
            _config = args[0]
            if isinstance(_config, self.config_cls):
                config = (
                    _config
                    if not kwargs
                    else self.config_cls.model_validate(_config.model_dump() | kwargs)
                )
            else:
                msg = f"positional arg is not a {self.config_cls.__name__} instance."
                raise ValueError(
                    msg,
                )
        else:
            msg = "too many positional args."
            raise ValueError(msg)
        self._config = cast("ConfigT", config)

    @property
    def config(self) -> ConfigT:
        """The step configuration object."""
        return self._config

    def create_context(self, data: Any) -> ContextT:
        """Create or replace this step's context on the data container.

        Parameters
        ----------
        data : object
            Container exposing an attrs or meta mapping.

        Returns
        -------
        StepContext
            New context with this step's producer, configuration, completed=False,
            and an empty failure list. Replaces the entry for this instance's
            alias without running the step or clearing results on the container.

        Raises
        ------
        TypeError
            The container has neither an attrs nor a meta mapping.
        """
        pctx = get_pipeline_contexts(data)
        context_cls = cast("type[ContextT]", self.context_cls)
        ctx = context_cls(
            step_cls=type(self),
            config=self._config,
            completed=False,
        )
        pctx[self.context_key] = ctx
        return ctx

    @classmethod
    def has_context(cls, data: Any, *, alias: str | None = None) -> bool:
        """Check whether this step has a stored context.

        Parameters
        ----------
        data : object
            Container exposing an attrs or meta mapping. An empty context store
            is attached on first lookup if none exists.
        alias : str or None, optional
            Invocation label. None selects the primary operation.

        Returns
        -------
        bool
            Whether this step's key is present, regardless of completion status.

        Raises
        ------
        TypeError
            The container has neither an attrs nor a meta mapping.
        """
        pctx = get_pipeline_contexts(data)
        return cls.get_context_key(alias=alias) in pctx

    @classmethod
    def get_context(cls, data: Any, *, alias: str | None = None) -> ContextT:
        """Return the typed context for this step from *data*.

        Parameters
        ----------
        data : Any
            Data container that has been processed by this step.
        alias : str or None, optional
            Invocation label. None selects the primary operation, including when
            this class method is called through a configured instance.

        Returns
        -------
        ContextT
            The attached live context, shared with the pipeline context store.

        Raises
        ------
        KeyError
            No context is stored for the requested alias.
        TypeError
            The container has neither an attrs nor a meta mapping.
        """
        pctx = get_pipeline_contexts(data)
        return cast("ContextT", pctx[cls.get_context_key(alias=alias)])

    @classmethod
    def run(cls, data: Any, context: ContextT) -> None:  # type: ignore[misc]
        """Perform this operation on the shared working data.

        Subclasses select their inputs from the available data and prior step
        contexts. Record failures when the operation cannot complete, including
        before an early return. Subsequent steps decide which results they require.

        Parameters
        ----------
        data : Any
            The data container (``xr.DataTree`` or similar).
        context : ContextT
            This invocation's context for recording step-specific state. Append
            StepFailure instances to ``context.failures`` as failures occur.

        Returns
        -------
        None
            Results and failures are stored on the data and context. A containing
            SequentialPipeline continues after a normal return, including when
            failures were recorded.

        Raises
        ------
        NotImplementedError
            The subclass has not implemented this method.
        """
        raise NotImplementedError

    @overload
    def __call__(
        self,
        data: Any,
        *,
        return_context: Literal[True],
    ) -> tuple[Any, ContextT]: ...

    @overload
    def __call__(
        self,
        data: Any,
        *,
        return_context: Literal[False] = ...,
    ) -> Any: ...

    def __call__(self, data: Any, *, return_context: bool = False) -> Any:
        """Run the step, storing context in *data*.

        Each call replaces the context for this instance's alias. After a normal
        return, the context is marked complete only when no failures were recorded.
        Direct calls run even when ``config.enabled`` is False.
        Lazy results are evaluated only if ``run()`` requests their computation.

        Parameters
        ----------
        data : Any
            Data container to process.
        return_context : bool, optional
            If ``True``, return ``(data, context)`` instead of just ``data``.

        Returns
        -------
        Any or tuple[Any, ContextT]
            The supplied data container, possibly mutated, plus context if requested.

        Raises
        ------
        TypeError
            The container has neither an attrs nor a meta mapping.
        Exception
            Exceptions escaping ``run()`` are recorded on the attached context
            and re-raised. Earlier failures and data mutations remain. Process
            control exceptions such as KeyboardInterrupt propagate without a record.
        """
        context = self.create_context(data)
        try:
            self.run(data, context)
        except Exception as exc:
            context.failures.append(
                StepFailure(
                    message=str(exc),
                    kind=StepFailureKind.exception,
                    exception_type=type(exc).__name__,
                )
            )
            raise
        context.completed = not context.failures
        if return_context:
            return data, context
        return data

    @classmethod
    def get_context_key(cls, *, alias: str | None = None) -> str:
        """Return the context key for an invocation.

        Parameters
        ----------
        alias : str or None, optional
            Invocation label. None selects the primary operation.

        Returns
        -------
        str
            Key for looking up this step's context in the working data.
        """
        name = getname(cls)
        return f"{name}:{alias}" if alias is not None else name

    @classmethod
    def dump_context(cls, context: ContextT) -> str:
        """Serialize this step's context as JSON for export.

        Parameters
        ----------
        context : StepContext
            This producer's invocation context. Its model field exclusions apply;
            exclude live views or other objects that cannot be serialized.

        Returns
        -------
        str
            JSON containing the included context fields. The caller chooses where
            to store it and reads it with this step's ``load_context()``.

        Raises
        ------
        pydantic_core.PydanticSerializationError
            An included value cannot be serialized as JSON.
        """
        return context.model_dump_json()

    @classmethod
    def load_context(cls, value: ContextT | str | Mapping[str, Any]) -> ContextT:
        """Read a live or exported context for this step.

        Parameters
        ----------
        value : StepContext, str, or mapping
            This producer's live context, JSON from ``dump_context()``, or decoded
            context fields. Use the original producing class; exported fields
            do not identify it. The saved configuration includes the invocation
            alias.

        Returns
        -------
        StepContext
            The live context unchanged, or a validated context that can recreate
            this step with ``make_step()``. Loading does not attach the returned
            context to a data container. Excluded fields take their model defaults;
            result views are not reconstructed.

        Raises
        ------
        json.JSONDecodeError
            The string is not valid JSON.
        pydantic.ValidationError
            The decoded value is not a context object, or its fields fail
            validation as this step's context model.
        """
        if isinstance(value, StepContext):
            return cast("ContextT", value)
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, Mapping):
            value = {**value, "step_cls": cls}
        return cast("ContextT", cls.context_cls.model_validate(value))


# ---------------------------------------------------------------------------
# Pipeline containers
# ---------------------------------------------------------------------------


class Pipeline:
    """Abstract pipeline base class."""

    @staticmethod
    def get_contexts(data: Any) -> StepContextDict:
        """Return the pipeline context dictionary for a container.

        Parameters
        ----------
        data : object
            Container exposing an attrs or meta mapping.

        Returns
        -------
        StepContextDict
            Attached context store, created empty on first access.
        """
        return get_pipeline_contexts(data)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Run the pipeline."""
        raise NotImplementedError


@dataclass(kw_only=True)
class SequentialPipeline(Pipeline):
    """Pipeline that executes a list of :class:`Step` instances sequentially.

    Steps with ``config.enabled = False`` are logged and skipped; any context from
    an earlier call remains. A step
    recording failures in ``run()`` leaves its context incomplete; later steps
    still run and select their own inputs. Exceptions propagate and stop the
    sequence. Changes made before stopping remain.

    Parameters
    ----------
    steps : list[Step]
        Ordered list of steps to execute.

    Examples
    --------
    >>> import xarray as xr
    >>> class CountConfig(StepConfig):
    ...     increment: int = 1
    >>> class CountContext(StepContext["CountStep", CountConfig]):
    ...     data: int = 0
    >>> class CountStep(Step[CountConfig, CountContext]):
    ...     @classmethod
    ...     def run(cls, data, context):
    ...         context.data = context.config.increment
    ...         data.attrs["count"] = context.data
    >>> pipeline = SequentialPipeline(steps=[CountStep(increment=3)])
    >>> data = pipeline(xr.Dataset())
    >>> CountStep.get_context(data).data
    3
    """

    steps: list[Step]

    @timeit  # type: ignore[invalid-argument-type]
    def __call__(self, data: Any) -> Any:
        """Run enabled operations in order on the working data.

        Parameters
        ----------
        data : object
            Working container passed to each step.

        Returns
        -------
        object
            The working container after all enabled operations have run.
            Recorded failures do not stop the sequence; an exception does.
        """
        _data = data
        for step in self.steps:
            if step.config.enabled:
                _data = step(_data)
            else:
                logger.debug(
                    f"step {step.context_key!r} is disabled, skipping",
                )
        return _data
