"""Pipeline step base classes.

Provides a typed, context-aware pipeline system over ``xr.DataTree`` (or any
container with an ``.attrs`` dict).  The design mirrors the v2
``tolteca_kids.pipeline`` module, adapted for v3 xarray-first data model:

- Context is stored in ``data.attrs["__pipeline_context__"]`` (equivalent to
  v2's ``data.meta["__pipeline_context__"]``).
- :class:`Step` subclasses declare typed :class:`StepConfig` /
  :class:`StepContext` generic parameters; ``Step.get_context(data)`` returns
  the typed context without dict-key lookups at the call site.
- :class:`SequentialPipeline` executes a list of steps in order, skipping
  disabled ones.

Typical usage::

    class MyConfig(StepConfig):
        threshold: float = 0.5

    class MyData(BaseModel):
        result: float | None = None

    class MyContext(StepContext["MyStep", MyConfig]):
        data: MyData | None = None

    class MyStep(Step[MyConfig, MyContext]):
        @classmethod
        def run(cls, data, context):
            context.data = MyData(result=42.0)
            return True

    step = MyStep(threshold=0.9)
    data = step(data)                          # executes, stores context in data.attrs
    ctx = MyStep.get_context(data)             # typed MyContext
    ctx.data.result                            # 42.0
"""

from __future__ import annotations

from collections import UserDict
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    TypeVar,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field

from ..utils.log import logger, timeit
from ..utils.py import getname
from ..utils.typing import get_typing_args

if TYPE_CHECKING:
    from typing import Self

__all__ = [
    "PIPELINE_CONTEXT_KEY",
    "Pipeline",
    "SequentialPipeline",
    "Step",
    "StepConfig",
    "StepContext",
    "StepContextDict",
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
    is honoured by :class:`SequentialPipeline` to skip disabled steps.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(default=True, description="Set False to skip this step.")


class StepContext[StepT: "Step", ConfigT: "StepConfig"](BaseModel):
    """Per-step state object stored in ``data.attrs[PIPELINE_CONTEXT_KEY]``.

    Subclasses override ``data`` with a typed field holding step outputs
    (tables, arrays, pydantic models).  The ``config`` field records the
    config that produced this context (useful for cache invalidation).
    ``completed`` is set to ``True`` by :class:`Step.__call__` after
    :meth:`Step.run` returns ``True``.

    Notes
    -----
    ``step_cls`` and ``config_cls`` are :class:`~typing.ClassVar` back-links
    injected by :meth:`Step.__init_subclass__`.
    """

    step_cls: ClassVar[type[Any]]
    config_cls: ClassVar[type[Any]]

    config: ConfigT
    data: None = None
    completed: bool = False

    def make_step(self) -> StepT:
        """Reconstruct the step from the stored config."""
        return self.step_cls(self.config)  # type: ignore[return-value]


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
            The context key string.
        """
        if isinstance(arg, str):
            return arg
        if isinstance(arg, type) and issubclass(arg, Step):
            return arg.context_key
        if isinstance(arg, Step):
            return type(arg).context_key
        if callable(arg):
            return getname(arg)
        msg = f"invalid step context key arg: {arg!r}"
        raise TypeError(msg)

    def __setitem__(self, key: Any, value: Any) -> None:  # type: ignore[override]
        super().__setitem__(self.resolve_key(key), value)

    def __getitem__(self, key: Any) -> Any:  # type: ignore[override]
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
    Accounts for the ``alias()`` mechanism.
    """

    def __get__(self, obj: Any, cls: type | None = None) -> str:
        if cls is None:
            cls = type(obj)
        basename: str = getattr(cls, "_orig_context_key", None) or getname(cls)
        alias: str | None = getattr(cls, "_alias_name", None)
        if alias:
            return f"{basename}_{alias}"
        return basename


# ---------------------------------------------------------------------------
# Step base class
# ---------------------------------------------------------------------------


class Step[ConfigT: "StepConfig", ContextT: "StepContext"]:
    """Base class for a typed, context-aware pipeline step.

    Subclasses declare their config and context types as Generic parameters::

        class MyStep(Step[MyConfig, MyContext]):
            @classmethod
            def run(cls, data, context):
                ...
                return True

    The step instance holds its config.  Calling the step on *data*:

    1. Creates a :class:`StepContext` in ``data.attrs["__pipeline_context__"]``.
    2. Calls :meth:`run`.
    3. Sets ``context.completed = True`` if :meth:`run` returns ``True``.

    Cross-step access is typed::

        ctx = OtherStep.get_context(data)   # returns OtherStepContext
        ctx.data.my_table                   # typed, no dict key needed
    """

    config_cls: ClassVar[type[StepConfig]]
    context_cls: ClassVar[type[StepContext]]
    _alias_name: ClassVar[str | None] = None
    _orig_context_key: ClassVar[str | None] = None

    context_key: ClassVar[str] = _ContextKeyDescriptor()  # type: ignore[assignment]

    _config: ConfigT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        config_cls = get_typing_args(
            cls,
            max_depth=2,
            bound=StepConfig,
            unique=True,
        )
        if config_cls is not None:
            cls.config_cls = config_cls

        context_cls = get_typing_args(
            cls,
            max_depth=2,
            bound=StepContext,
            unique=True,
        )
        if context_cls is not None:
            cls.context_cls = context_cls
            cls.context_cls.step_cls = cls  # type: ignore[attr-defined]
            cls.context_cls.config_cls = cls.config_cls  # type: ignore[attr-defined]

        return super().__init_subclass__(**kwargs)

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
        self._config = config  # type: ignore[assignment]

    @property
    def config(self) -> ConfigT:
        """The step configuration object."""
        return self._config  # type: ignore[return-value]

    def create_context(self, data: Any) -> ContextT:
        """Create (or replace) this step's context on *data*."""
        pctx = get_pipeline_contexts(data)
        ctx: ContextT = self.context_cls(  # type: ignore[call-arg]
            config=self._config,
            completed=False,
        )
        pctx[self.context_key] = ctx
        return ctx

    @classmethod
    def has_context(cls, data: Any) -> bool:
        """Return ``True`` if a context for this step exists on *data*."""
        pctx = get_pipeline_contexts(data)
        return cls.context_key in pctx

    @classmethod
    def get_context(cls, data: Any) -> ContextT:
        """Return the typed context for this step from *data*.

        Parameters
        ----------
        data : Any
            Data container that has been processed by this step.

        Returns
        -------
        ContextT
            The typed step context.

        Raises
        ------
        KeyError
            If this step has not run on *data* yet.
        """
        pctx = get_pipeline_contexts(data)
        return pctx[cls.context_key]  # type: ignore[return-value]

    @classmethod
    def run(cls, data: Any, context: ContextT) -> bool:  # type: ignore[misc]
        """Execute the step's computation.

        Subclasses must implement this.  Populate ``context.data`` with
        outputs.  Return ``True`` on success (sets ``context.completed``).

        Parameters
        ----------
        data : Any
            The data container (``xr.DataTree`` or similar).
        context : ContextT
            The step's context object — write outputs here.

        Returns
        -------
        bool
            ``True`` if the step completed successfully.
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

        Parameters
        ----------
        data : Any
            Data container to process.
        return_context : bool, optional
            If ``True``, return ``(data, context)`` instead of just ``data``.

        Returns
        -------
        Any or tuple[Any, ContextT]
            The (possibly mutated) data container, plus context if requested.
        """
        context = self.create_context(data)
        if self.run(data, context):
            context.completed = True
        if return_context:
            return data, context
        return data

    @classmethod
    def alias(cls, name: str) -> type[Self]:
        """Return a step subclass with an alternative context key.

        Useful when the same step class is used twice in one pipeline with
        different configs (e.g. two ``KidsFind`` passes).

        Parameters
        ----------
        name : str
            Suffix appended to the base context key.

        Returns
        -------
        type[Self]
            A new step class sharing implementation but with a distinct key.
        """
        return type(  # type: ignore[return-value]
            cls.__name__,
            (cls,),
            {
                "_alias_name": name,
                "_orig_context_key": getattr(cls, "_orig_context_key", None)
                or cls.context_key,
            },
        )


# ---------------------------------------------------------------------------
# Pipeline containers
# ---------------------------------------------------------------------------


class Pipeline:
    """Abstract pipeline base class."""

    @staticmethod
    def get_contexts(data: Any) -> StepContextDict:
        """Return the pipeline context dict for *data*."""
        return get_pipeline_contexts(data)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Run the pipeline."""
        raise NotImplementedError


@dataclass(kw_only=True)
class SequentialPipeline(Pipeline):
    """Pipeline that executes a list of :class:`Step` instances sequentially.

    Steps with ``config.enabled = False`` are logged and skipped.

    Parameters
    ----------
    steps : list[Step]
        Ordered list of steps to execute.

    Examples
    --------
    >>> pipeline = SequentialPipeline(steps=[StepA(...), StepB(...)])
    >>> data = pipeline(raw_data)
    >>> StepA.get_context(data).data   # typed access
    """

    steps: list[Step]

    @timeit  # type: ignore[invalid-argument-type]
    def __call__(self, data: Any) -> Any:
        """Execute all enabled steps sequentially."""
        _data = data
        for step in self.steps:
            if step.config.enabled:
                _data = step(_data)
            else:
                logger.debug(
                    f"step {type(step).context_key!r} is disabled, skipping",
                )
        return _data
