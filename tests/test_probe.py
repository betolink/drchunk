from drchunk._probe import _classify_coord, _parse_date_path


class TestClassifyCoord:
    def test_latitude_variants(self):
        assert _classify_coord("lat") == "lat"
        assert _classify_coord("latitude") == "lat"
        assert _classify_coord("Latitude") == "lat"
        assert _classify_coord("y") == "lat"

    def test_longitude_variants(self):
        assert _classify_coord("lon") == "lon"
        assert _classify_coord("longitude") == "lon"
        assert _classify_coord("lng") == "lon"
        assert _classify_coord("x") == "lon"

    def test_time_variants(self):
        assert _classify_coord("time") == "time"
        assert _classify_coord("t") == "time"
        assert _classify_coord("datetime") == "time"

    def test_altitude_variants(self):
        assert _classify_coord("alt") == "alt"
        assert _classify_coord("altitude") == "alt"
        assert _classify_coord("elevation") == "alt"
        assert _classify_coord("z") == "alt"

    def test_non_coord(self):
        assert _classify_coord("temperature") is None
        assert _classify_coord("precip") is None
        assert _classify_coord("") is None
        assert _classify_coord("data") is None

    def test_nested_paths(self):
        assert _classify_coord("lat") == "lat"
        assert _classify_coord("LAT") == "lat"


class TestParseDatePath:
    def test_yyyymmdd(self):
        from datetime import datetime
        d = _parse_date_path("/data/20240115_something.nc")
        assert d == datetime(2024, 1, 15)

    def test_yyyy_mm_dd(self):
        from datetime import datetime
        d = _parse_date_path("/data/sst_2024-06-30.nc")
        assert d == datetime(2024, 6, 30)

    def test_yyyy_mm_dd_underscore(self):
        from datetime import datetime
        d = _parse_date_path("/data/var_2024_12_01_v2.nc")
        assert d == datetime(2024, 12, 1)

    def test_no_date(self):
        assert _parse_date_path("/data/file.nc") is None
        assert _parse_date_path("just_a_name") is None

    def test_multiple_dates_uses_first(self):
        from datetime import datetime
        d = _parse_date_path("20200101_20200201.nc")
        assert d == datetime(2020, 1, 1)
