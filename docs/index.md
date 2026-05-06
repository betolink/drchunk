# Dr. Chunk

Extract chunking and codec metadata from HDF5/NetCDF4 files.
Verify dataset homogeneity, visualize chunk discrepancies over time, and generate
human-readable reports — all parallelized with Dask.

## Install

```bash
pip install drchunk
# optional: earthaccess for remote CMR granules
pip install drchunk[remote]
```

## Quickstart

### 1. Sample granules from a CMR collection

Instead of inspecting thousands of files, `sample()` queries the collection's
temporal extent and picks one random granule per time slice:

```python
import drchunk

granules = drchunk.sample(
    short_name="MODIS_Terra_NDVI",
    freq="Y",          # one per year
    seed=42,           # reproducible picks
)
```

### 2. Extract chunking and codec metadata

```python
df = drchunk.info(granules)
```

The DataFrame contains `url`, `date`, `variables`, `coords`, and `error` columns.
Each variable entry records `shape`, `chunks`, `dtype`, and `codecs`.

### 3. Generate a homogeneity report

```python
print(drchunk.report(df))
```

```
================================================================
  Dr. Chunk  —  Chunking & Codec Homogeneity Report
================================================================

  Granules inspected : 12
  Date range         : 2002-12-31  →  2025-12-31

  ■ temperature  (12 granules)
    Chunk shapes:
      (50, 200)                    12  100.0% ████████████████████
    Codecs:
      gzip                         12  100.0% ████████████████████
    ...

  Fully homogeneous (≥99.9%)  : 4
    ✓ lat  ✓ lon  ✓ temperature  ✓ time

  Overall score : 100% of variables are fully homogeneous.
```

### 4. Visualize interactively

```python
widget = drchunk.visualize(df)
widget.show()   # opens in browser
```

### CLI

```bash
# Sample + inspect + report in one pass
drchunk run --short-name MODIS_Terra_NDVI -f Y

# Inspect local files
drchunk info *.nc

# Generate report
drchunk report *.nc -o report.txt

# Interactive widget
drchunk visualize *.nc
```
