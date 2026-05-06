from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dask import delayed
from dask.delayed import Delayed

if TYPE_CHECKING:
    import h5py

# ---------------------------------------------------------------------------
# Coord heuristics
# ---------------------------------------------------------------------------

COORD_PATTERNS = {
    "lat": re.compile(r"^(lat(itude)?|y)$", re.IGNORECASE),
    "lon": re.compile(r"^(lon(gitude)?|lng|x)$", re.IGNORECASE),
    "time": re.compile(r"^(time|t|date|datetime)$", re.IGNORECASE),
    "alt": re.compile(r"^(alt(itude)?|elevation|height|z)$", re.IGNORECASE),
}


def _classify_coord(name: str) -> str | None:
    for canonical, pattern in COORD_PATTERNS.items():
        if pattern.match(name):
            return canonical
    return None


# ---------------------------------------------------------------------------
# Per-dataset metadata (shape + chunks + dtype + codecs)
# ---------------------------------------------------------------------------


def _dataset_meta(ds: h5py.Dataset) -> dict[str, Any]:
    import h5py

    meta = {
        "shape": ds.shape,
        "chunks": ds.chunks,
        "dtype": str(ds.dtype),
        "codecs": [],
    }

    KNOWN = {
        h5py.h5z.FILTER_DEFLATE: "gzip",
        h5py.h5z.FILTER_SHUFFLE: "shuffle",
        h5py.h5z.FILTER_FLETCHER32: "fletcher32",
        h5py.h5z.FILTER_SZIP: "szip",
        h5py.h5z.FILTER_NBIT: "nbit",
        h5py.h5z.FILTER_SCALEOFFSET: "scaleoffset",
    }

    dcpl = ds.id.get_create_plist()
    for i in range(dcpl.get_nfilters()):
        code, flags, data, name = dcpl.get_filter(i)
        meta["codecs"].append(
            {
                "name": KNOWN.get(code, name or str(code)),
                "code": code,
                "flags": flags,
                "opts": list(data),
            }
        )

    return meta


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _parse_date(g: dict) -> datetime | None:
    try:
        date_str = g["umm"]["TemporalExtent"]["RangeDateTime"][
            "EndingDateTime"
        ].replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    except (KeyError, AttributeError):
        pass
    return None


def _parse_date_path(path: str) -> datetime | None:
    """Attempt to extract a date from a file path. Tries common patterns."""
    import os

    name = os.path.basename(path)
    # Try YYYYMMDD, YYYY-MM-DD, YYYY_MM_DD
    patterns = [
        (re.compile(r"(\d{4})(\d{2})(\d{2})"), "%Y%m%d"),
        (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),
        (re.compile(r"(\d{4})_(\d{2})_(\d{2})"), "%Y_%m_%d"),
    ]
    for pat, _fmt in patterns:
        m = pat.search(name)
        if m:
            return datetime.strptime(f"{m[1]}{m[2]}{m[3]}", "%Y%m%d")
    return None


# ---------------------------------------------------------------------------
# Local file probing
# ---------------------------------------------------------------------------


def _probe_local(path: str) -> dict:
    import os

    import h5py

    out: dict[str, Any] = {
        "url": os.path.abspath(path),
        "date": _parse_date_path(path),
        "variables": {},
        "coords": {},
        "codecs_global": [],
        "error": "",
    }

    try:
        with h5py.File(path, "r") as h:

            def _walk(name: str, node: h5py.Dataset) -> None:
                if not isinstance(node, h5py.Dataset):
                    return

                meta = _dataset_meta(node)
                canonical = _classify_coord(name.split("/")[-1])

                if canonical:
                    out["coords"].setdefault(canonical, []).append(
                        {"path": name, **meta}
                    )
                else:
                    out["variables"][name] = meta

            h.visititems(_walk)

    except Exception as e:
        out["error"] = str(e)

    return out


# ---------------------------------------------------------------------------
# EarthAccess granule probing (remote)
# ---------------------------------------------------------------------------


def _probe_earthaccess(g: dict) -> dict[str, Any]:
    import earthaccess
    import h5py

    out: dict[str, Any] = {
        "url": g["meta"]["concept-id"],
        "date": _parse_date(g),
        "variables": {},
        "coords": {},
        "codecs_global": [],
        "error": "",
    }

    try:
        earthaccess.login(strategy="all")
        f = earthaccess.open([g])[0]

        with h5py.File(f, "r") as h:

            def _walk(name: str, node: h5py.Dataset) -> None:
                if not isinstance(node, h5py.Dataset):
                    return

                meta = _dataset_meta(node)
                canonical = _classify_coord(name.split("/")[-1])

                if canonical:
                    out["coords"].setdefault(canonical, []).append(
                        {"path": name, **meta}
                    )
                else:
                    out["variables"][name] = meta

            h.visititems(_walk)

    except Exception as e:
        out["error"] = str(e)

    return out


# ---------------------------------------------------------------------------
# Public API — lazy probe
# ---------------------------------------------------------------------------


def probe(path_or_granule: str | dict) -> Delayed:
    """
    Lazy inspection of a granule (earthaccess) or local HDF5/NetCDF4 file.
    Returns full variable + coord metadata (no data loaded).

    Returns a dask.delayed object wrapping the result dict.

    Usage
    -----
    results = dask.compute(*[probe(p) for p in paths])
    """
    if isinstance(path_or_granule, dict):
        return delayed(_probe_earthaccess)(path_or_granule)
    return delayed(_probe_local)(path_or_granule)
