"""
Temporal sampling — query CMR for a collection, pick one random granule
per time slice, return granules ready for ``drchunk.info()``.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime

import pandas as pd


def _normalize_freq(freq: str) -> str:
    """Convert user-friendly freq to pandas 3.x offset alias."""
    import re
    m = re.match(r"(\d*)([A-Za-z]+)", freq)
    if not m:
        return freq
    num, base = m.group(1), m.group(2)
    mapping = {"D": "D", "W": "W-SUN", "M": "ME", "Y": "YE"}
    if base.upper() in mapping:
        return num + mapping[base.upper()]
    return freq


def _now_utc() -> str:
    from datetime import timezone
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date_str(s: str) -> datetime:
    """Parse an ISO-8601 string, stripping trailing Z if present."""
    s = s.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def sample(
    concept_id: str | None = None,
    short_name: str | None = None,
    freq: str = "M",
    seed: int | None = None,
    max_granules: int = 100,
) -> list[dict]:
    """
    Query CMR for a collection, then sample one random granule per time slice.

    Parameters
    ----------
    concept_id : str, optional
        CMR concept ID (e.g. ``C1234567890-PROV``).
    short_name : str, optional
        Collection short name (e.g. ``MODIS_Terra_NDVI``).  Used if
        ``concept_id`` is not supplied.
    freq : str
        Pandas offset alias for time-slice frequency:
        ``"D"`` daily, ``"W"`` weekly, ``"M"`` monthly, ``"Y"`` yearly.
        Default ``"M"``.
    seed : int, optional
        Seed for reproducible random date picks.
    max_granules : int
        Maximum number of slices/granules to return. Raises ValueError
        if the chosen frequency would produce more slices. Default 100.

    Returns
    -------
    list[dict]
        EarthAccess granule dicts, ready to pass to ``drchunk.info()``.
    """
    import earthaccess

    if not concept_id and not short_name:
        raise ValueError("Provide concept_id or short_name")

    earthaccess.login(strategy="all")

    if seed is not None:
        random.seed(seed)

    # -- 1. fetch collection metadata ----------------------------------------
    if concept_id:
        datasets = earthaccess.search_datasets(concept_id=concept_id)
    else:
        datasets = earthaccess.search_datasets(short_name=short_name)

    if not datasets:
        raise ValueError("No collections found in CMR")

    ds = datasets[0]
    umm = ds.get("umm", {})
    meta = ds.get("meta", {})

    cid = meta.get("concept-id", concept_id or short_name)

    # -- 2. extract temporal extent ------------------------------------------
    temporal_extents = umm.get("TemporalExtents", [])
    if not temporal_extents:
        raise ValueError(f"Collection {cid} has no TemporalExtents in UMM")

    range_dates = temporal_extents[0].get("RangeDateTimes", [])
    if not range_dates:
        raise ValueError(f"Collection {cid} has no RangeDateTimes")

    r = range_dates[0]
    begin = _parse_date_str(r["BeginningDateTime"])
    end = _parse_date_str(r.get("EndingDateTime", _now_utc()))

    # -- 3. calculate total granule count (if resolution available) ----------
    temporal_res = temporal_extents[0].get("TemporalResolution", "")
    estimated_granules = _estimate_granule_count(begin, end, temporal_res)

    # -- 4. build time slices and pick random dates --------------------------
    freq_alias = _normalize_freq(freq)

    boundaries = pd.date_range(begin, end, freq=freq_alias, tz="UTC")
    if len(boundaries) == 0:
        raise ValueError(f"Date range {begin} → {end} too short for freq={freq}")
    if len(boundaries) > max_granules:
        raise ValueError(
            f"freq={freq} produces {len(boundaries)} slices (> max_granules={max_granules}). "
            f"Use a coarser frequency or raise max_granules."
        )

    # Build (slice_start, slice_end) pairs
    slices: list[tuple[datetime, datetime]] = []
    for i, b in enumerate(boundaries):
        s_start = b.to_pydatetime()
        s_end = boundaries[i + 1].to_pydatetime() if i + 1 < len(boundaries) else end
        slices.append((s_start, s_end))

    # -- 5. decide strategy: bulk vs per-slice queries -----------------------
    import earthaccess

    THRESHOLD = 20_000

    if estimated_granules is not None and estimated_granules <= THRESHOLD:
        # Small collection — one query, bin locally
        all_granules = earthaccess.search_data(
            concept_id=cid,
            temporal=(
                begin.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
            ),
        )
        granules = _bin_and_pick(all_granules, slices)
    else:
        # Large collection — query per slice to avoid pulling millions of results
        granules = _query_per_slice(cid, slices)

    # -- 6. summary ------------------------------------------------------------
    _log_sample(begin, end, estimated_granules, freq, len(granules), len(boundaries))

    return granules


# ---------------------------------------------------------------------------
# sampling strategies
# ---------------------------------------------------------------------------


def _bin_and_pick(
    all_granules: list[dict],
    slices: list[tuple[datetime, datetime]],
) -> list[dict]:
    """Bin granules by start date into time slices, pick one per slice."""
    bins: dict[int, list[dict]] = defaultdict(list)

    for g in all_granules:
        g_start = _granule_start_date(g)
        if g_start is None:
            continue
        for i, (s_start, s_end) in enumerate(slices):
            if s_start <= g_start < s_end:
                bins[i].append(g)
                break

    return _pick_from_bins(bins, len(slices))


def _query_per_slice(
    cid: str,
    slices: list[tuple[datetime, datetime]],
) -> list[dict]:
    """Query CMR for one random day per time slice, pick a granule from each."""
    from datetime import timedelta

    import earthaccess

    picked: list[dict] = []
    seen: set[str] = set()

    for s_start, s_end in slices:
        # Pick a random day within this slice
        delta = (s_end - s_start)
        if delta.days <= 1:
            day = s_start
        else:
            day = s_start + timedelta(days=random.randint(0, delta.days - 1))
        day_str = day.strftime("%Y-%m-%d")

        try:
            results = earthaccess.search_data(
                concept_id=cid,
                temporal=(day_str, day_str),
            )
        except Exception:
            continue

        candidates = [
            g for g in results
            if g.get("meta", {}).get("concept-id") not in seen
        ]
        if not candidates:
            continue

        pick = random.choice(candidates)
        picked.append(pick)
        seen.add(pick.get("meta", {}).get("concept-id"))

    return picked


def _pick_from_bins(
    bins: dict[int, list[dict]],
    num_slices: int,
) -> list[dict]:
    """Randomly pick one granule from each non-empty bin."""
    picked: list[dict] = []
    for i in range(num_slices):
        candidates = bins.get(i, [])
        if candidates:
            picked.append(random.choice(candidates))
    return picked


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _granule_start_date(g: dict) -> datetime | None:
    """Extract BeginningDateTime from a granule's UMM TemporalExtent."""
    try:
        raw = g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
        return _parse_date_str(raw)
    except (KeyError, TypeError):
        return None


def _estimate_granule_count(
    begin: datetime, end: datetime, resolution: str
) -> int | None:
    """Try to parse a UMM TemporalResolution ISO-8601 duration string."""
    if not resolution:
        return None

    total_seconds = (end - begin).total_seconds()

    # ISO 8601 duration: P[nY][nM][nD][T[nH][nM][nS]]
    # Note: M before T = months; M after T = minutes
    import re
    m = re.match(
        r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?"
        r"(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
        resolution,
    )
    if not m:
        return None

    years = int(m.group(1) or 0)
    months = int(m.group(2) or 0)
    days = int(m.group(3) or 0)
    hours = int(m.group(4) or 0)
    minutes = int(m.group(5) or 0)
    seconds = float(m.group(6) or 0)

    # Approximate years and months in seconds
    step_seconds = (
        years * 365.25 * 86400
        + months * 30.4375 * 86400
        + days * 86400
        + hours * 3600
        + minutes * 60
        + seconds
    )
    if step_seconds <= 0:
        return None

    return max(1, int(total_seconds / step_seconds))


def _log_sample(
    begin: datetime,
    end: datetime,
    estimated: int | None,
    freq: str,
    found: int,
    total_slices: int,
) -> None:
    """Print a sampling summary to stderr (not mixed with stdout output)."""
    import sys

    est_str = f"{estimated:,}" if estimated else "unknown"
    print(
        f"\nDr. Chunk sample: {begin.date()} → {end.date()}  "
        f"(~{est_str} granules)  freq={freq}  "
        f"→ {found}/{total_slices} slices matched\n",
        file=sys.stderr,
    )
