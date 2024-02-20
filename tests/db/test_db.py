from tollan.db.core import SqlaDB


def test_sqladb_url():
    sqla = SqlaDB.from_url("sqlite:///:memory:")
    assert sqla.metadata is not None
