"""
Text report generator for chunking/codec analysis.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd


def _safe_items(d: object) -> list[tuple[str, object]]:
    """Extract (key, meta) pairs, flattening list-valued coords to first entry."""
    if not isinstance(d, dict):
        return []
    result = []
    for k, v in d.items():
        if isinstance(v, list):
            if v and isinstance(v[0], dict):
                result.append((k, v[0]))
        elif isinstance(v, dict):
            result.append((k, v))
    return result


def _extract_codecs(meta: dict) -> list[str]:
    """Return a sorted tuple of codec names for a variable's metadata."""
    codecs = meta.get("codecs", [])
    if not codecs:
        return []
    return sorted(c["name"] for c in codecs)


def _extract_chunks(meta: dict) -> tuple | None:
    """Return chunk shape as a tuple, or None."""
    chunks = meta.get("chunks")
    if chunks is None:
        return None
    return tuple(chunks)


def _extract_dtype(meta: dict) -> str:
    return str(meta.get("dtype", "?"))


def generate(df: pd.DataFrame) -> str:
    """
    Generate a human-readable report from an info DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame as returned by ``drchunk.info()``.

    Returns
    -------
    str
        Multi-line text report.
    """
    lines = []
    _w = lines.append

    # -- header ------------------------------------------------
    _w("=" * 64)
    _w("  Dr. Chunk  —  Chunking & Codec Homogeneity Report")
    _w("=" * 64)

    # -- basic stats -------------------------------------------
    total = len(df)
    errors = 0
    if "error" in df.columns:
        errors = int((df["error"].notna() & (df["error"] != "")).sum())

    _w(f"\n  Granules inspected : {total}")
    if errors:
        _w(f"  Errors             : {errors}  ({errors/total*100:.1f}%)")
    else:
        _w("  Errors             : 0")

    # -- date range --------------------------------------------
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], utc=True, errors="coerce").dropna()
        if not dates.empty:
            _w(f"  Date range         : {dates.min().date()}  →  {dates.max().date()}")

    # -- aggregate all variables across all rows ---------------
    # Collect all variable names (from both "variables" and "coords")
    all_vars: set[str] = set()
    for col in ("variables", "coords"):
        if col in df.columns:
            for entry in df[col].dropna():
                if isinstance(entry, dict):
                    all_vars.update(entry.keys())
    all_vars = sorted(all_vars)

    if not all_vars:
        _w("\n  No variables or coordinates found.")
        return "\n".join(lines)

    # -- per-variable analysis ---------------------------------
    _w(f"\n{'─' * 64}")
    _w(f"  Variables / Coordinates found : {len(all_vars)}")
    _w(f"{'─' * 64}")

    # Homogeneity score tracking
    variable_summaries: list[dict] = []

    for var in all_vars:
        chunk_counts: Counter = Counter()
        codec_counts: Counter = Counter()
        dtype_counts: Counter = Counter()
        ndim_counts: Counter = Counter()
        granule_count = 0

        for col in ("variables", "coords"):
            if col not in df.columns:
                continue
            for entry in df[col].dropna():
                if not isinstance(entry, dict):
                    continue
                meta = entry.get(var)
                if meta is None:
                    continue
                if isinstance(meta, list):
                    if not meta:
                        continue
                    meta = meta[0]
                granule_count += 1

                chunks = _extract_chunks(meta)
                if chunks is not None:
                    chunk_counts[chunks] += 1
                    ndim_counts[len(chunks)] += 1

                codecs = tuple(_extract_codecs(meta))
                codec_counts[codecs] += 1

                dtype_counts[_extract_dtype(meta)] += 1

        if granule_count == 0:
            continue

        # Homogeneity scores
        total_chunk_entries = sum(chunk_counts.values())
        top_chunk = chunk_counts.most_common(1)
        chunk_pct = (top_chunk[0][1] / total_chunk_entries * 100) if top_chunk else 0

        total_codec_entries = sum(codec_counts.values())
        top_codec = codec_counts.most_common(1)
        codec_pct = (top_codec[0][1] / total_codec_entries * 100) if top_codec else 0

        variable_summaries.append({
            "name": var,
            "granules": granule_count,
            "chunk_pct": chunk_pct,
            "codec_pct": codec_pct,
        })

        _w(f"\n  ■ {var}  ({granule_count} granules)")
        _w("    Chunk shapes:")
        if not chunk_counts:
            _w("      (none — contiguous / no chunking)")
        else:
            for shape, count in chunk_counts.most_common():
                bar = _spark(count, total_chunk_entries, width=20)
                _w(f"      {str(shape):24s}  {count:5d}  {count/total_chunk_entries*100:5.1f}% {bar}")

        _w("    Codecs:")
        if not codec_counts or all(k == () for k in codec_counts):
            _w("      (none / uncompressed)")
        else:
            for codec_tuple, count in codec_counts.most_common():
                label = ", ".join(codec_tuple) if codec_tuple else "(none)"
                bar = _spark(count, total_codec_entries, width=20)
                _w(f"      {label:24s}  {count:5d}  {count/total_codec_entries*100:5.1f}% {bar}")

        _w("    Dtypes:")
        for dt, count in dtype_counts.most_common():
            pct = count / granule_count * 100
            _w(f"      {dt:24s}  {count:5d}  {pct:5.1f}%")

    # -- overall homogeneity assessment ------------------------
    _w(f"\n{'═' * 64}")
    _w("  Homogeneity Assessment")
    _w(f"{'═' * 64}")

    if not variable_summaries:
        _w("\n  No data to assess.")
        return "\n".join(lines)

    full_homogeneous = []
    partial_homogeneous = []
    heterogeneous = []

    for vs in variable_summaries:
        if vs["chunk_pct"] >= 99.9 and vs["codec_pct"] >= 99.9:
            full_homogeneous.append(vs["name"])
        elif vs["chunk_pct"] >= 80 and vs["codec_pct"] >= 80:
            partial_homogeneous.append(vs["name"])
        else:
            heterogeneous.append(vs["name"])

    _w(f"\n  Fully homogeneous (≥99.9%)  : {len(full_homogeneous)}")
    for name in full_homogeneous:
        _w(f"    ✓ {name}")

    _w(f"\n  Mostly homogeneous (≥80%)   : {len(partial_homogeneous)}")
    for name in partial_homogeneous:
        vs = next(v for v in variable_summaries if v["name"] == name)
        _w(f"    ~ {name}  (chunk={vs['chunk_pct']:.0f}%  codec={vs['codec_pct']:.0f}%)")

    _w(f"\n  Heterogeneous (<80%)        : {len(heterogeneous)}")
    for name in heterogeneous:
        vs = next(v for v in variable_summaries if v["name"] == name)
        _w(f"    ✗ {name}  (chunk={vs['chunk_pct']:.0f}%  codec={vs['codec_pct']:.0f}%)")

    overall = len(full_homogeneous) / len(variable_summaries) * 100
    _w(f"\n  Overall score : {overall:.0f}% of variables are fully homogeneous.")

    if heterogeneous:
        _w("\n  ⚠  Consider reprocessing or excluding files covering the")
        _w("     heterogeneous variables listed above.")
    elif partial_homogeneous:
        _w("\n  ℹ  Most variables are consistent. Review the partial outliers")
        _w("     to decide on action.")

    _w(f"\n{'─' * 64}")
    _w("  Report generated by Dr. Chunk")
    _w(f"{'─' * 64}")

    return "\n".join(lines)


def _spark(count: int, total: int, width: int = 20) -> str:
    """Mini bar chart using block characters."""
    if total == 0:
        return ""
    frac = count / total
    filled = int(frac * width)
    if filled == 0 and count > 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)
