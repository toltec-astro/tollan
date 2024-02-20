import dataclasses

__all__ = ["get_dataclass_fields", "get_dataclass_field_default"]


def get_dataclass_fields(cls, *names):
    """Return the fields in dataclass."""
    fields_by_name = {name: None for name in names}
    for field in dataclasses.fields(cls):
        name = field.name
        if name in fields_by_name:
            fields_by_name[name] = field
    return fields_by_name


def get_dataclass_field_default(field: dataclasses.Field):
    """Return the field default value."""
    MISSING = dataclasses.MISSING  # noqa: N806
    if field.default is MISSING and field.default_factory is MISSING:
        raise ValueError(f"{field.name} does not have a default.")
    if field.default is not MISSING and field.default_factory is not MISSING:
        raise ValueError(f"{field.name} has too many defaults.")
    if field.default is not MISSING:
        return field.default
    return field.default_factory()
