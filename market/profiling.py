"""Dataset profiling: every number in the data documentation comes from here."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def profile(df: pd.DataFrame, name: str, list_columns: tuple[str, ...] = ()) -> dict:
    """Shape, types, missing values, duplicates, cardinality and numeric summaries."""
    hashable = df.drop(columns=[c for c in list_columns if c in df.columns])
    hashable = hashable.apply(lambda s: s.astype(str) if s.map(lambda v: isinstance(v, (list, dict))).any() else s)
    columns = {}
    for col in df.columns:
        s = df[col]
        info = {
            "dtype": str(s.dtype),
            "missing": int(s.isna().sum()),
            "missing_pct": round(float(s.isna().mean() * 100), 2),
        }
        if col not in list_columns:
            try:
                info["unique"] = int(s.nunique(dropna=True))
            except TypeError:
                info["unique"] = int(s.astype(str).nunique())
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            desc = s.describe(percentiles=[0.25, 0.5, 0.75])
            info["stats"] = {k: _jsonable(v) for k, v in desc.items() if k != "count"}
        elif pd.api.types.is_bool_dtype(s):
            info["true_pct"] = round(float(s.mean() * 100), 2)
        columns[col] = info
    return {
        "name": name,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_rows": int(hashable.duplicated().sum()),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 1),
        "column_profiles": columns,
    }


def top_counts(series: pd.Series, n: int = 15) -> list[dict]:
    counts = series.value_counts(dropna=False).head(n)
    total = len(series)
    return [{"value": None if pd.isna(k) else str(k), "count": int(v), "pct": round(v / total * 100, 2)}
            for k, v in counts.items()]
