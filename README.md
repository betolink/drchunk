# Dr. Chunk

Extract chunking and codec metadata from HDF5/NetCDF4 files.
Verify dataset homogeneity, visualize chunk discrepancies over time, and generate
human-readable reports — all parallelized with Dask.

## Install

```bash
pip install drchunk
pip install drchunk[remote]  # for CMR/earthaccess support
```

## Quickstart

```python
import drchunk

# Sample one random granule per year from a CMR collection
granules = drchunk.sample(short_name="MODIS_Terra_NDVI", freq="Y", seed=42)

# Extract chunking/codec metadata (parallelized with Dask)
df = drchunk.info(granules)

# Print a homogeneity report
print(drchunk.report(df))

# Launch the interactive timeline widget
drchunk.visualize(df).show()
```

## CLI

```bash
drchunk run --short-name MODIS_Terra_NDVI -f Y   # sample + inspect + report
drchunk info *.nc                                 # inspect local files
drchunk report *.nc                               # text report
drchunk visualize *.nc                            # interactive widget
```

## Development

```bash
pip install -e ".[dev]"
ruff check .          # lint
pytest -m "not integration"   # unit tests
pytest -m integration         # CMR integration tests (needs credentials)
mkdocs serve          # docs
```
