from datetime import datetime, timezone

import pytest

from drchunk._sample import (
    _bin_and_pick,
    _estimate_granule_count,
    _granule_start_date,
    _parse_date_str,
    _pick_from_bins,
    sample,
)


class TestParseDateStr:
    def test_with_fractional_seconds(self):
        d = _parse_date_str("2020-01-15T12:30:45.123Z")
        assert d.year == 2020
        assert d.month == 1
        assert d.day == 15
        assert d.tzinfo is not None

    def test_without_fractional_seconds(self):
        d = _parse_date_str("2020-06-30T23:59:59Z")
        assert d.month == 6
        assert d.day == 30

    def test_date_only(self):
        d = _parse_date_str("2000-03-15Z")
        assert d.year == 2000
        assert d.month == 3

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_date_str("not-a-date")


class TestEstimateGranuleCount:
    tz = timezone.utc
    begin = datetime(2020, 1, 1, tzinfo=tz)
    end = datetime(2020, 12, 31, tzinfo=tz)

    def test_hourly(self):
        assert _estimate_granule_count(self.begin, self.end, "PT1H") == 8760

    def test_daily(self):
        assert _estimate_granule_count(self.begin, self.end, "P1D") == 365

    def test_monthly(self):
        count = _estimate_granule_count(self.begin, self.end, "P1M")
        assert count == 11

    @pytest.mark.parametrize("res,expected", [
        ("P1Y", 1),
        ("PT30M", 17520),
    ])
    def test_parametrized(self, res, expected):
        assert _estimate_granule_count(self.begin, self.end, res) == expected

    def test_empty_resolution(self):
        assert _estimate_granule_count(self.begin, self.end, "") is None

    def test_unparseable_resolution(self):
        assert _estimate_granule_count(self.begin, self.end, "garbage") is None


class TestGranuleStartDate:
    def test_valid(self):
        g = {"umm": {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2020-03-15T00:00:00Z"}}}}
        d = _granule_start_date(g)
        assert d.year == 2020
        assert d.month == 3

    def test_missing_umm(self):
        assert _granule_start_date({"umm": {}}) is None

    def test_missing_umm_entirely(self):
        assert _granule_start_date({}) is None


class TestPickFromBins:
    def test_one_per_bin(self):
        bins = {
            0: [{"id": "a"}, {"id": "b"}],
            1: [{"id": "c"}],
        }
        result = _pick_from_bins(bins, 3)
        assert len(result) == 2  # bin 2 empty, skipped
        assert result[0] in bins[0]
        assert result[1] in bins[1]

    def test_empty_bins(self):
        assert _pick_from_bins({}, 5) == []

    def test_seed_reproducible(self):
        import random
        bins = {i: [{"id": j} for j in range(10)] for i in range(3)}
        random.seed(42)
        r1 = _pick_from_bins(bins, 3)
        random.seed(42)
        r2 = _pick_from_bins(bins, 3)
        assert r1 == r2


class TestBinAndPick:
    def test_distributes_granules(self):
        from datetime import datetime, timezone
        tz = timezone.utc
        slices = [
            (datetime(2020, 1, 1, tzinfo=tz), datetime(2020, 2, 1, tzinfo=tz)),
            (datetime(2020, 2, 1, tzinfo=tz), datetime(2020, 3, 1, tzinfo=tz)),
        ]
        granules = [
            {"umm": {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2020-01-15T00:00:00Z"}}}},
            {"umm": {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2020-01-20T00:00:00Z"}}}},
            {"umm": {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2020-02-10T00:00:00Z"}}}},
        ]
        result = _bin_and_pick(granules, slices)
        assert len(result) == 2

    def test_granule_outside_all_slices_ignored(self):
        from datetime import datetime, timezone
        tz = timezone.utc
        slices = [
            (datetime(2020, 1, 1, tzinfo=tz), datetime(2020, 2, 1, tzinfo=tz)),
        ]
        granules = [
            {"umm": {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2020-06-01T00:00:00Z"}}}},
        ]
        result = _bin_and_pick(granules, slices)
        assert len(result) == 0

    def test_missing_dates_ignored(self):
        slices = [(datetime(2020, 1, 1), datetime(2020, 2, 1))]
        result = _bin_and_pick([{"umm": {}}], slices)
        assert result == []


class TestSampleValidation:
    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="concept_id or short_name"):
            sample()
