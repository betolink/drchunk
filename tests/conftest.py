import pandas as pd
import pytest


@pytest.fixture
def sample_df():
    """Two granules: homogeneous temperature, heterogeneous precipitation."""
    return pd.DataFrame([
        {
            "url": "file_a.nc",
            "date": "2020-01-15T00:00:00Z",
            "variables": {
                "temperature": {
                    "shape": (100, 200),
                    "chunks": (50, 200),
                    "dtype": "float32",
                    "codecs": [{"name": "gzip", "code": 1, "flags": 0, "opts": [4]}],
                },
                "precip": {
                    "shape": (100, 200),
                    "chunks": (50, 200),
                    "dtype": "float32",
                    "codecs": [{"name": "gzip", "code": 1, "flags": 0, "opts": [4]}],
                },
            },
            "coords": {
                "lat": [{"path": "/lat", "shape": (200,), "chunks": (200,), "dtype": "float64", "codecs": []}],
                "time": [{"path": "/time", "shape": (100,), "chunks": (100,), "dtype": "float64", "codecs": []}],
            },
            "error": "",
        },
        {
            "url": "file_b.nc",
            "date": "2020-02-15T00:00:00Z",
            "variables": {
                "temperature": {
                    "shape": (100, 200),
                    "chunks": (50, 200),
                    "dtype": "float32",
                    "codecs": [{"name": "gzip", "code": 1, "flags": 0, "opts": [4]}],
                },
                "precip": {
                    "shape": (100, 200),
                    "chunks": (100, 100),
                    "dtype": "float32",
                    "codecs": [{"name": "shuffle", "code": 2, "flags": 0, "opts": []}],
                },
            },
            "coords": {
                "lat": [{"path": "/lat", "shape": (200,), "chunks": (200,), "dtype": "float64", "codecs": []}],
            },
            "error": "",
        },
    ])


@pytest.fixture
def single_var_df():
    """One granule, one variable, no coords."""
    return pd.DataFrame([
        {
            "url": "file.nc",
            "date": "2020-01-01T00:00:00Z",
            "variables": {
                "sst": {
                    "shape": (360, 180),
                    "chunks": (180, 180),
                    "dtype": "float64",
                    "codecs": [{"name": "gzip", "code": 1, "flags": 0, "opts": [9]}],
                },
            },
            "coords": {},
            "error": "",
        },
    ])


@pytest.fixture
def error_df():
    """Two granules: one OK, one with error."""
    return pd.DataFrame([
        {
            "url": "ok.nc",
            "date": "2020-01-01T00:00:00Z",
            "variables": {"var": {"shape": (10,), "chunks": (10,), "dtype": "int16", "codecs": []}},
            "coords": {},
            "error": "",
        },
        {
            "url": "bad.nc",
            "date": "2020-01-02T00:00:00Z",
            "variables": {},
            "coords": {},
            "error": "permission denied",
        },
    ])
