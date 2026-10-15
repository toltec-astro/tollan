"""SQLite aggregate functions used by portable SQL queries."""

from sqlalchemy import event


class _BitwiseOr:
    def __init__(self):
        self.value = 0

    def step(self, value):
        self.value |= value

    def finalize(self):
        return self.value


class _BitwiseAnd(_BitwiseOr):
    def __init__(self):
        self.value = -1

    def step(self, value):
        self.value &= value


def _register_bitwise(dbapi_connection, _connection_record, _connection_proxy):
    dbapi_connection.create_aggregate("bit_or", 1, _BitwiseOr)
    dbapi_connection.create_aggregate("bit_and", 1, _BitwiseAnd)


def _register_bitwise_aggregates(engine):
    """Install aggregates on new and already-pooled SQLite connections."""
    if not event.contains(engine, "checkout", _register_bitwise):
        event.listen(engine, "checkout", _register_bitwise)
