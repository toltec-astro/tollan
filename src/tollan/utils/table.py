from dataclasses import dataclass

from astropy.table import QTable, Table


@dataclass
class TableValidator:
    """A validator for table."""

    table_cls: type[Table] = Table | QTable

    def validate_cols(self, tbl: Table, cols):
        """Return existing cols in the table."""
        return [c for c in cols if c in tbl.colnames]

    def has_any_col(self, tbl: Table, cols: list[str]):
        """Return true if table has any cols."""
        return len(self.validate_cols(tbl, cols)) > 0

    def has_all_cols(self, tbl: Table, cols: list[str]):
        """Return true if table has all cols."""
        return len(self.validate_cols(tbl, cols)) == len(cols)

    def get_first_col(self, tbl: Table, cols: list[str]):
        """Return the first existing col."""
        cols = self.validate_cols(tbl, cols)
        if len(cols) == 0:
            return None
        return cols[0]

    def get_first_col_data(self, tbl: Table, cols):
        """Return column data for cols."""
        col = self.get_first_col(tbl, cols)
        return tbl[col] if col is not None else None

    def get_col_data(self, tbl: Table, cols):
        """Return column data for cols."""
        return [tbl[c] if c in tbl.colnames else None for c in cols]

    def validate_meta(self, meta: dict, keys):
        """Return existing keys in the table metadata."""
        return [k for k in keys if k in meta]

    def has_any_meta(self, meta: dict, keys: list[str]):
        """Return true if table meta has any keys."""
        return len(self.validate_meta(meta, keys)) > 0

    def has_all_meta(self, meta: dict, keys: list[str]):
        """Return true if table meta has all keys."""
        return len(self.validate_meta(meta, keys)) == len(keys)

    def get_first_meta(self, meta: dict, keys: list[str]):
        """Return the first existing key."""
        keys = self.validate_meta(meta, keys)
        if len(keys) == 0:
            return None
        return keys[0]

    def get_first_meta_value(self, meta: dict, keys):
        """Return metadata for first key in keys."""
        key = self.get_first_meta(meta, keys)
        return meta[key] if key is not None else None

    def get_meta_values(self, meta: dict, keys):
        """Return metadata for keys."""
        return [meta.get(k) for k in keys]
