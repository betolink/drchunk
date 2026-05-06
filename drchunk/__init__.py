"""
Dr. Chunk — Extract chunking and codec information from HDF5/NetCDF4 files.

High-level API:
    granules = drchunk.sample(short_name="...", freq="Y")
    df = drchunk.info(granules)
    drchunk.visualize(df)
    print(drchunk.report(df))
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import dask
import pandas as pd

from drchunk._probe import probe
from drchunk._report import generate as _generate_report
from drchunk._sample import sample  # noqa: F401  # re-exported
from drchunk._timeline import ChunkTimeline

if TYPE_CHECKING:
    import panel as pn


def info(paths: list, npartitions: int | None = None) -> pd.DataFrame:
    """
    Inspect a list of file paths (or earthaccess granules) and return a DataFrame
    with chunking, codec, and coordinate metadata.

    Parameters
    ----------
    paths : list[str] | list[dict]
        List of local HDF5/NetCDF4 file paths, or list of earthaccess granule dicts.
    npartitions : int, optional
        Number of Dask partitions for parallelism. Defaults to number of files.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: url, date, variables, coords, error.
        Each row corresponds to one input file/granule.
    """
    probes = [probe(p) for p in paths]
    results = dask.compute(*probes)
    return pd.DataFrame(list(results))


def visualize(df: pd.DataFrame) -> pn.viewable.Viewable:
    """
    Create an interactive Panel widget for visualizing chunk size timelines.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame as returned by ``drchunk.info()``.

    Returns
    -------
    pn.viewable.Viewable
        A Panel layout with variable selector, chunk dimension selector,
        aggregation controls, and a HoloViews timeline plot.
    """
    ct = ChunkTimeline(df)
    return ct.widget()


def report(df: pd.DataFrame) -> str:
    """
    Generate a human-readable text report summarizing chunking/codec homogeneity.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame as returned by ``drchunk.info()``.

    Returns
    -------
    str
        Multi-line text report.
    """
    return _generate_report(df)
