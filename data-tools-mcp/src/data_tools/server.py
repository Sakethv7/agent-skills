"""
data-tools MCP server

Tools for profiling, inspecting, and querying structured data — files (CSV,
Excel, Parquet, JSON) and databases (PostgreSQL, SQLite, MySQL via SQLAlchemy).

Merges two concerns that always appear together: schema inspection (what does
the data look like structurally?) and data profiling (what does it actually
contain?).

Dependencies: pandas, openpyxl, sqlalchemy, pyarrow (pip)
"""

import json
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "data-tools",
    instructions=(
        "Tools for profiling and querying structured data. "
        "For files: use profile_file for a full analysis, or load_file + "
        "describe_columns for targeted inspection. "
        "For databases: use list_tables first, then describe_table, then "
        "sample_rows. Always use find_column when you're not sure which table "
        "contains a field."
    ),
)


def _load_df(path: str):
    """Load a file into a pandas DataFrame."""
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pip install pandas openpyxl pyarrow")

    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".csv":
        return pd.read_csv(path)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    elif ext == ".parquet":
        return pd.read_parquet(path)
    elif ext == ".json":
        return pd.read_json(path)
    elif ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Supported: csv, xlsx, xls, parquet, json, tsv")


def _safe_val(v) -> Any:
    """Convert numpy/pandas types to JSON-safe Python types."""
    try:
        import numpy as np
        import pandas as pd
        if pd.isna(v):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except Exception:
        pass
    return v


# ---------------------------------------------------------------------------
# File profiling tools
# ---------------------------------------------------------------------------


@mcp.tool()
def profile_file(path: str, sample_n: int = 5) -> dict:
    """
    Full profile of a data file: shape, schema, null counts, uniqueness,
    numeric distributions, top values, and quality issues. Works on CSV,
    Excel, Parquet, JSON, TSV.

    Args:
        path: Absolute path to the data file.
        sample_n: Number of sample rows to include (default 5).
    """
    import pandas as pd
    df = _load_df(path)
    p = Path(path)

    columns = []
    for col in df.columns:
        s = df[col]
        dtype = str(s.dtype)
        null_count = int(s.isna().sum())
        unique_count = int(s.nunique(dropna=True))
        entry: dict = {
            "name": col,
            "dtype": dtype,
            "null_count": null_count,
            "null_pct": round(null_count / len(df) * 100, 1) if len(df) else 0,
            "unique_count": unique_count,
            "unique_pct": round(unique_count / len(df) * 100, 1) if len(df) else 0,
        }

        if pd.api.types.is_numeric_dtype(s):
            desc = s.describe()
            entry.update({
                "min": _safe_val(desc.get("min")),
                "max": _safe_val(desc.get("max")),
                "mean": _safe_val(desc.get("mean")),
                "median": _safe_val(s.median()),
                "std": _safe_val(desc.get("std")),
                "p25": _safe_val(desc.get("25%")),
                "p75": _safe_val(desc.get("75%")),
            })
            # Outlier count using IQR
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            outlier_count = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
            entry["outlier_count"] = outlier_count
        else:
            top = s.value_counts().head(5)
            entry["top_values"] = [
                {"value": str(v), "count": int(c)} for v, c in top.items()
            ]

        columns.append(entry)

    # Quality issues
    issues = []
    for col in df.columns:
        s = df[col]
        null_pct = s.isna().mean() * 100
        if null_pct > 50:
            issues.append({"column": col, "issue": "high_nulls", "detail": f"{null_pct:.0f}% null"})
        if s.nunique() == 1:
            issues.append({"column": col, "issue": "constant_column", "detail": f"all values are '{s.iloc[0]}'"})
        if str(s.dtype) == "object" and s.nunique() < 10 and len(df) > 100:
            issues.append({"column": col, "issue": "low_cardinality_string",
                           "detail": f"{s.nunique()} unique values — consider categorical dtype"})

    dup_count = int(df.duplicated().sum())
    if dup_count:
        issues.append({"column": None, "issue": "duplicate_rows", "detail": f"{dup_count} duplicate rows"})

    return {
        "path": path,
        "file_size_bytes": p.stat().st_size,
        "rows": len(df),
        "columns": len(df.columns),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2),
        "duplicate_rows": dup_count,
        "schema": columns,
        "quality_issues": issues,
        "sample": df.head(sample_n).to_dict(orient="records"),
    }


@mcp.tool()
def list_sheets(path: str) -> list[dict]:
    """
    For Excel files: list all sheets with their dimensions.

    Args:
        path: Absolute path to the .xlsx or .xls file.
    """
    import pandas as pd
    xl = pd.ExcelFile(path)
    result = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, nrows=0)
        full = xl.parse(sheet)
        result.append({
            "sheet": sheet,
            "rows": len(full),
            "columns": len(full.columns),
            "column_names": list(full.columns),
        })
    return result


@mcp.tool()
def sample_file(path: str, n: int = 20, sheet: Optional[str] = None) -> list[dict]:
    """
    Return a sample of rows from a data file. For Excel, specify a sheet name.

    Args:
        path: Absolute path to the data file.
        n: Number of rows to sample (default 20).
        sheet: Sheet name for Excel files (default: first sheet).
    """
    import pandas as pd
    if sheet:
        df = pd.read_excel(path, sheet_name=sheet)
    else:
        df = _load_df(path)
    return df.head(n).to_dict(orient="records")


@mcp.tool()
def find_column_in_file(path: str, pattern: str, sheet: Optional[str] = None) -> list[dict]:
    """
    Search for columns matching a pattern (case-insensitive substring or regex)
    in a data file. Useful when you're not sure what a column is called.

    Args:
        path: Absolute path to the data file.
        pattern: Substring or regex to match against column names.
        sheet: Sheet name for Excel files.
    """
    import pandas as pd, re
    if sheet:
        df = pd.read_excel(path, sheet_name=sheet)
    else:
        df = _load_df(path)

    matches = [
        {"column": col, "dtype": str(df[col].dtype)}
        for col in df.columns
        if re.search(pattern, str(col), re.IGNORECASE)
    ]
    return matches


@mcp.tool()
def compare_schemas(path_a: str, path_b: str) -> dict:
    """
    Compare the schemas of two data files. Returns columns only in A, only in B,
    columns in both but with different dtypes, and shared columns.

    Args:
        path_a: Absolute path to the first file.
        path_b: Absolute path to the second file.
    """
    df_a = _load_df(path_a)
    df_b = _load_df(path_b)

    cols_a = {col: str(df_a[col].dtype) for col in df_a.columns}
    cols_b = {col: str(df_b[col].dtype) for col in df_b.columns}

    only_a = [{"column": c, "dtype": cols_a[c]} for c in cols_a if c not in cols_b]
    only_b = [{"column": c, "dtype": cols_b[c]} for c in cols_b if c not in cols_a]
    shared = [c for c in cols_a if c in cols_b]
    type_mismatch = [
        {"column": c, "dtype_a": cols_a[c], "dtype_b": cols_b[c]}
        for c in shared if cols_a[c] != cols_b[c]
    ]
    matching = [c for c in shared if cols_a[c] == cols_b[c]]

    return {
        "only_in_a": only_a,
        "only_in_b": only_b,
        "type_mismatches": type_mismatch,
        "matching_columns": matching,
        "total_a": len(cols_a),
        "total_b": len(cols_b),
        "overlap": len(shared),
    }


# ---------------------------------------------------------------------------
# Database tools
# ---------------------------------------------------------------------------


def _engine(connection_string: str):
    try:
        from sqlalchemy import create_engine
        return create_engine(connection_string)
    except ImportError:
        raise RuntimeError("pip install sqlalchemy")


@mcp.tool()
def list_tables(connection_string: str, schema: Optional[str] = None) -> list[str]:
    """
    List all tables in a database.

    Args:
        connection_string: SQLAlchemy connection string.
          Examples:
            postgresql://user:pass@localhost/mydb
            sqlite:///path/to/file.db
            mysql+pymysql://user:pass@localhost/mydb
        schema: Schema name (for databases that support schemas).
    """
    from sqlalchemy import inspect
    engine = _engine(connection_string)
    inspector = inspect(engine)
    return inspector.get_table_names(schema=schema)


@mcp.tool()
def describe_table(connection_string: str, table: str, schema: Optional[str] = None) -> dict:
    """
    Describe a database table: columns, types, nullable, defaults, primary keys,
    foreign keys, and indexes.

    Args:
        connection_string: SQLAlchemy connection string.
        table: Table name.
        schema: Schema name (optional).
    """
    from sqlalchemy import inspect, text
    engine = _engine(connection_string)
    inspector = inspect(engine)

    columns = [
        {
            "name": col["name"],
            "type": str(col["type"]),
            "nullable": col.get("nullable", True),
            "default": str(col.get("default")) if col.get("default") else None,
        }
        for col in inspector.get_columns(table, schema=schema)
    ]
    pk = inspector.get_pk_constraint(table, schema=schema)
    fks = inspector.get_foreign_keys(table, schema=schema)
    indexes = inspector.get_indexes(table, schema=schema)

    # Row count
    with engine.connect() as conn:
        qualified = f"{schema}.{table}" if schema else table
        row_count = conn.execute(text(f"SELECT COUNT(*) FROM {qualified}")).scalar()

    return {
        "table": table,
        "schema": schema,
        "row_count": row_count,
        "columns": columns,
        "primary_keys": pk.get("constrained_columns", []),
        "foreign_keys": fks,
        "indexes": indexes,
    }


@mcp.tool()
def sample_rows(
    connection_string: str,
    table: str,
    n: int = 10,
    schema: Optional[str] = None,
    where: Optional[str] = None,
) -> list[dict]:
    """
    Return sample rows from a database table.

    Args:
        connection_string: SQLAlchemy connection string.
        table: Table name.
        n: Number of rows to return (default 10).
        schema: Schema name (optional).
        where: Optional WHERE clause (without the WHERE keyword).
    """
    from sqlalchemy import text
    engine = _engine(connection_string)
    qualified = f"{schema}.{table}" if schema else table
    query = f"SELECT * FROM {qualified}"
    if where:
        query += f" WHERE {where}"
    query += f" LIMIT {n}"

    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = [dict(zip(result.keys(), row)) for row in result]
    return rows


@mcp.tool()
def find_column(
    connection_string: str,
    pattern: str,
    schema: Optional[str] = None,
) -> list[dict]:
    """
    Search all tables in a database for columns matching a name pattern.
    Useful when you're not sure which table has a field.

    Args:
        connection_string: SQLAlchemy connection string.
        pattern: Case-insensitive substring to search for in column names.
        schema: Schema to search (default: all schemas).
    """
    import re
    from sqlalchemy import inspect
    engine = _engine(connection_string)
    inspector = inspect(engine)

    matches = []
    for table in inspector.get_table_names(schema=schema):
        for col in inspector.get_columns(table, schema=schema):
            if re.search(pattern, col["name"], re.IGNORECASE):
                matches.append({
                    "table": table,
                    "schema": schema,
                    "column": col["name"],
                    "type": str(col["type"]),
                })
    return matches


@mcp.tool()
def run_query(connection_string: str, sql: str, limit: int = 100) -> dict:
    """
    Execute a read-only SQL query and return results. Automatically appends
    LIMIT if not present to prevent accidental full-table scans.

    Only SELECT statements are allowed — raises an error for INSERT/UPDATE/DELETE.

    Args:
        connection_string: SQLAlchemy connection string.
        sql: SQL SELECT query.
        limit: Max rows to return (default 100). Ignored if query already has LIMIT.
    """
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed via run_query.")
    if "LIMIT" not in sql_clean.upper():
        sql_clean += f" LIMIT {limit}"

    from sqlalchemy import text
    engine = _engine(connection_string)
    with engine.connect() as conn:
        result = conn.execute(text(sql_clean))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result]

    return {"columns": columns, "rows": rows, "count": len(rows)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
